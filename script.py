import uuid
import aiohttp
import asyncio
import json
import os
from random import randint

DEBUG = False
MAX_RETRIES = 30
LOOP_DELAY = 2 * 60  # Delay between complete cycles in seconds (2 minutes)
games_url = "https://raw.githubusercontent.com/SP-l33t/GenofcodesHMSTR/main/games.json"
amount_of_files = 1000
games = None


def debug(*args):
    if DEBUG:
        print(*args)


def info(*args):
    print(*args)


async def fetch_api(session, path, method="post", auth_token=None, body=None):
    url = f"https://api.gamepromo.io{path}" if not path.startswith("http") else path
    headers = {}

    if auth_token:
        headers["authorization"] = f"Bearer {auth_token}"

    if body is not None:
        headers["content-type"] = "application/json"
    if method == "post":
        async with session.post(url, headers=headers, json=body) as response:
            debug(f"URL: {url}, Headers: {headers}, Body: {body}")
            if response.status != 200:
                error_message = await response.text()
                debug(f"Error {response.status}: {error_message}")
                raise Exception(f"{response.status} {response.reason}: {error_message}")
            return await response.json()

    elif method == "get":
        async with session.get(url) as response:
            if response.status != 200:
                error_message = await response.text()
                debug(f"Error {response.status}: {error_message}")
                raise Exception(f"{response.status} {response.reason}: {error_message}")
            return json.loads(await response.text())


async def get_promo_code(session, game_key):
    game_config = games[game_key]
    client_id = str(uuid.uuid4())

    try:
        login_client_data = await fetch_api(
            session,
            "/promo/login-client",
            body={
                "appToken": game_config["appToken"],
                "clientId": client_id,
                "clientOrigin": "ios",
            },
        )
    except Exception as e:
        info(f"Failed to login client for {game_key}: {e}")
        return None

    auth_token = login_client_data.get("clientToken")
    if not auth_token:
        info(f"Failed to obtain auth token for {game_key}")
        return None

    promo_code = None
    attempt = 0
    for _ in range(MAX_RETRIES):
        try:
            await asyncio.sleep(game_config["delay"])
            register_event_data = await fetch_api(
                session,
                "/promo/register-event",
                method="post",
                auth_token=auth_token,
                body={
                    "promoId": game_config["promoId"],
                    "eventId": str(uuid.uuid4()),
                    "eventOrigin": "undefined",
                },
            )
        except Exception as e:
            info(f"Failed to register event for {game_key}: {e}")
            attempt += 1
            await asyncio.sleep(min(game_config["retry"] * attempt, game_config["retry"] * 10))
            continue

        if not register_event_data.get("hasCode"):
            await asyncio.sleep(game_config["retry"])
            continue

        try:
            create_code_data = await fetch_api(
                session,
                "/promo/create-code",
                method="post",
                auth_token=auth_token,
                body={
                    "promoId": game_config["promoId"],
                },
            )
            promo_code = create_code_data.get("promoCode")
            break
        except Exception as e:
            info(f"Failed to create code for {game_key}: {e}")
            await asyncio.sleep(game_config["retry"])

    if not promo_code:
        info(f"Unable to get {game_key} promo after {MAX_RETRIES} retries")

    return promo_code


async def main():
    global games
    async with aiohttp.ClientSession() as session:
        for x in range(amount_of_files):
            file_path = f"promo_codes_{x}.txt"
            if os.path.exists(file_path):
                continue

            info('Refreshing games config')
            games = await fetch_api(session, games_url, method="get")
            promo_codes = []
            with open(file_path, "a") as f:
                async def write_promo_codes(game_key):
                    await asyncio.sleep(randint(1, 10))
                    codes = 0
                    while codes < games[game_key]["keys"]:
                        code = await get_promo_code(session, game_key)
                        if code:
                            info(f"{code}")
                            promo_codes.append(f"`{code}`\n")
                            codes += 1

                tasks = [write_promo_codes(game_key) for game_key in games]
                await asyncio.gather(*tasks)
                f.writelines(sorted(promo_codes))

            info(f"End of cycle. Wait {LOOP_DELAY} second before next cycle.")
            await asyncio.sleep(LOOP_DELAY)


if __name__ == "__main__":
    asyncio.run(main())
