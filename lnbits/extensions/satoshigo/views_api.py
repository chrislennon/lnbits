from quart import g, jsonify, request
from http import HTTPStatus

from lnbits.core.crud import get_user
from lnbits.decorators import api_check_wallet_key, api_validate_post_request
import random
import math

from .views import broadcast
from . import satoshigo_ext
from .crud import (
    create_satoshigo_game,
    get_satoshigo_game,
    get_satoshigo_game_player,
    get_satoshigo_games,
    update_satoshigo_game,
    delete_satoshigo_game,
    create_satoshigo_funding,
    get_satoshigo_funding,
    update_satoshigo_funding,
    get_satoshigo_fundings,
    create_satoshigo_player,
    get_satoshigo_player,
    get_satoshigo_players,
    update_satoshigo_player,
    create_satoshigo_item,
    update_satoshigo_item,
    get_satoshigo_player_inkey,
    get_satoshigo_admin_games,
    create_area,
    get_satoshigo_areas,
    get_satoshigo_area,
)
from ...core.services import create_invoice, check_invoice_status


@satoshigo_ext.route("/api/v1/admin/games", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_admin_games():
    wallet_ids = [g.wallet.id]

    if "all_wallets" in request.args:
        wallet_ids = (await get_user(g.wallet.user)).wallet_ids

    return (
        jsonify(
            [game._asdict() for game in await get_satoshigo_admin_games(wallet_ids)]
        ),
        HTTPStatus.OK,
    )


@satoshigo_ext.route("/api/v1/games", methods=["GET"])
async def api_games():

    return (
        jsonify([game._asdict() for game in await get_satoshigo_games()]),
        HTTPStatus.OK,
    )


@satoshigo_ext.route("/api/v1/games/<game_id>/admin", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_game_retrieve(game_id):
    game = await get_satoshigo_game(game_id)

    if not game:
        return (
            jsonify({"message": "satoshigo game does not exist."}),
            HTTPStatus.NOT_FOUND,
        )

    if game.wallet != g.wallet.id:
        return jsonify({"message": "Not your satoshigo game."}), HTTPStatus.FORBIDDEN

    return jsonify({**game._asdict()}), HTTPStatus.OK


@satoshigo_ext.route("/api/v1/games/<game_id>", methods=["GET"])
async def api_game_retrieve(game_id):
    game = await get_satoshigo_game_player(game_id)
    if not game:
        return (
            jsonify({"message": "Game does not exist."}),
            HTTPStatus.NOT_FOUND,
        )

    return jsonify({**game._asdict()}), HTTPStatus.OK


@satoshigo_ext.route("/api/v1/games", methods=["POST"])
@satoshigo_ext.route("/api/v1/games/<game_id>", methods=["PUT"])
@api_check_wallet_key("admin")
@api_validate_post_request(
    schema={
        "title": {"type": "string", "empty": False, "required": True},
        "description": {"type": "string", "empty": False, "required": True},
    }
)
async def api_game_create_or_update(game_id=None):
    if game_id:
        game = await get_satoshigo_game(game_id)
        if not game:
            return (
                jsonify({"message": "satoshigo game does not exist."}),
                HTTPStatus.NOT_FOUND,
            )
        if game.wallet != g.wallet.id:
            return (
                jsonify({"message": "Not your satoshigo game."}),
                HTTPStatus.FORBIDDEN,
            )
        game = await update_satoshigo_game(game_id, **g.data)
    else:
        game = await create_satoshigo_game(
            wallet=g.wallet.id, wallet_key=g.wallet.inkey, **g.data
        )
    return jsonify({**game._asdict()}), HTTPStatus.OK if game_id else HTTPStatus.CREATED


@satoshigo_ext.route("/api/v1/games/<game_id>", methods=["DELETE"])
@api_check_wallet_key("admin")
async def api_game_delete(game_id):
    game = await get_satoshigo_game(game_id)

    if not game:
        return (
            jsonify({"message": "satoshigo game does not exist."}),
            HTTPStatus.NOT_FOUND,
        )

    if game.wallet != g.wallet.id:
        return jsonify({"message": "Not your satoshigo game."}), HTTPStatus.FORBIDDEN

    await delete_satoshigo_game(game_id)

    return "", HTTPStatus.NO_CONTENT


###################################### FUNDING


@satoshigo_ext.route("/api/v1/funding/", methods=["POST"])
@api_validate_post_request(
    schema={
        "game_id": {"type": "string", "empty": False, "required": True},
        "tplat": {"type": "float", "empty": False, "required": True},
        "tplon": {"type": "float", "empty": False, "required": True},
        "btlat": {"type": "float", "empty": False, "required": True},
        "btlon": {"type": "float", "empty": False, "required": True},
        "sats": {"type": "integer", "empty": False, "required": True},
    }
)
async def api_game_fund():
    game = await get_satoshigo_game(g.data["game_id"])

    if not game:
        return (
            jsonify({"message": "satoshigo game does not exist."}),
            HTTPStatus.NOT_FOUND,
        )

    payment_hash, payment_request = await create_invoice(
        wallet_id=game.wallet,
        amount=g.data["sats"],
        memo="game_id",
    )

    funding = await create_satoshigo_funding(
        game_id=game.id,
        wallet=game.wallet,
        tplat=g.data["tplat"],
        tplon=g.data["tplon"],
        btlat=g.data["btlat"],
        btlon=g.data["btlon"],
        amount=g.data["sats"],
        payment_hash=payment_hash,
    )

    return jsonify({**funding._asdict()}, payment_request), HTTPStatus.OK


@satoshigo_ext.route("/api/v1/funding/<game_id>/<payment_hash>", methods=["GET"])
async def api_game_check_funding(game_id, payment_hash):
    game = await get_satoshigo_game(game_id)
    check = await check_invoice_status(game.wallet, payment_hash)
    if not game:
        return jsonify({"message": "Game does not exist."}), HTTPStatus.NOT_FOUND
    if check.paid:
        funding = await get_satoshigo_funding(payment_hash)
        if funding.confirmed == False:
            funding = await update_satoshigo_funding(payment_hash, confirmed=True)
            await cAreaMaker(
                funding.amount,
                funding.tplon,
                funding.tplat,
                funding.btlon,
                funding.btlat,
                game_id,
            )
            await update_satoshigo_game(game_id, amount=game.amount + funding.amount)
        return jsonify({**check._asdict()}), HTTPStatus.OK

    return jsonify({**check._asdict()}), HTTPStatus.OK


@satoshigo_ext.route("/api/v1/funding/<funding_id>", methods=["GET"])
async def api_game_funding(funding_id):
    funding = await get_satoshigo_funding(funding_id)
    return jsonify(funding._asdict()), HTTPStatus.OK


###################################### ITEMS


@satoshigo_ext.route("/api/v1/items", methods=["POST"])
@satoshigo_ext.route("/api/v1/items/<item_id>", methods=["PUT"])
@api_check_wallet_key("admin")
@api_validate_post_request(
    schema={
        "type": {"type": "string", "empty": False, "required": True},
        "areaHash": {"type": "string", "empty": False, "required": True},
        "data": {"type": "string", "empty": False, "required": True},
        "appearance": {"type": "string", "empty": False, "required": True},
    }
)
async def api_game_item_post(item_id):
    if item_id:
        item = await update_satoshigo_item(item_id, **g.data)
    else:
        item = await create_satoshigo_item(**g.data)
    return jsonify(item), HTTPStatus.CREATED


@satoshigo_ext.route("/api/v1/items/<player_id>/collect", methods=["GET"])
async def api_game_player_get(player_id):
    player = await get_satoshigo_player(player_id)
    return jsonify(player._asdict()), HTTPStatus.CREATED


###################################### CAREAS


async def cAreaMaker(someSats, tplng, tplat, btlng, btlat, gameHash):
    pot = 0
    numPots = 0
    lngs = []
    lats = []

    if 10 <= someSats <= 20:
        noAreas = 2
        itemsPArea = 1
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 20 <= someSats <= 50:
        noAreas = 4
        itemsPArea = 2
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 50 <= someSats <= 100:
        noAreas = 5
        itemsPArea = 2
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 100 <= someSats <= 500:
        noAreas = 10
        itemsPArea = 2
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 500 <= someSats <= 1000:
        noAreas = 20
        itemsPArea = 2
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 1000 <= someSats <= 5000:
        noAreas = 30
        itemsPArea = 3
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 5000 <= someSats <= 10000:
        noAreas = 40
        itemsPArea = 3
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if 10000 <= someSats <= 100000:
        noAreas = 50
        itemsPArea = random.randint(2, 4)
        itemValue = math.floor(someSats / (noAreas * itemsPArea))
    if someSats >= 100000:
        noAreas = 100
        itemsPArea = random.randint(2, 6)
        itemValue = math.floor(someSats / (noAreas * itemsPArea))

    for areaNo in range(noAreas):
        items = []
        lngs.append(random.uniform(tplng, btlng))
        lats.append(random.uniform(tplat, btlat))
        area_id = await create_area(lngs[areaNo], lats[areaNo], 10, gameHash)
        for item in areaNo:
            items.append(
                await create_satoshigo_item("simple", area_id, itemValue, "coin")
            )
        area = await get_satoshigo_area(area_id)
        await broadcast(str(jsonify({{"area": area}, {"items": items}})))

    return ""


@satoshigo_ext.route("/api/v1/find/areas", methods=["POST"])
@api_validate_post_request(
    schema={
        "lon": {"type": "float", "empty": False, "required": True},
        "lat": {"type": "float", "empty": False, "required": True},
        "radius": {"type": "integer", "empty": False, "required": True},
    }
)
async def api_game_get_areas():
    areas = await get_satoshigo_areas(**g.data)
    return jsonify([area._asdict() for area in areas]), HTTPStatus.OK


@satoshigo_ext.route("/api/v1/find/areas/<area_id>", methods=["GET"])
async def api_game_get_area(area_id):
    area = await get_satoshigo_area(area_id)
    return jsonify(area._asdict()), HTTPStatus.OK


###################################### PLAYERS


@satoshigo_ext.route("/api/v1/players", methods=["POST"])
@api_validate_post_request(
    schema={"user_name": {"type": "string", "empty": False, "required": True}}
)
async def api_game_player_post():
    player = await create_satoshigo_player(g.data["user_name"])
    return jsonify(player._asdict()), HTTPStatus.CREATED


@satoshigo_ext.route("/api/v1/players/<player_id>", methods=["PUT"])
@api_check_wallet_key("admin")
@api_validate_post_request(
    schema={"user_name": {"type": "string", "empty": False, "required": True}}
)
async def api_game_player_update(player_id):
    player = await update_satoshigo_player(g.data["user_name"], player_id)
    return jsonify(player._asdict()), HTTPStatus.CREATED


@satoshigo_ext.route("/api/v1/players/<player_id>", methods=["GET"])
async def api_game_player_get(player_id):
    player = await get_satoshigo_player(player_id)
    return jsonify(player._asdict()), HTTPStatus.CREATED


###################################### ENTER GAME


@satoshigo_ext.route("/api/v1/games/<game_id>/enter", methods=["POST"])
@api_validate_post_request(
    schema={"inkey": {"type": "string", "empty": False, "required": True}}
)
async def api_game_enter(game_id):
    player = await get_satoshigo_player_inkey(g.data["inkey"])
    await update_satoshigo_player(player.id, gameHash=game_id)
    game = get_satoshigo_game(game_id)
    return jsonify(game._asdict()), HTTPStatus.CREATED


@satoshigo_ext.route("/api/v1/games/players", methods=["GET"])
@api_check_wallet_key("inkey")
async def api_games_players():
    wallet_ids = [g.wallet.id]
    if "all_wallets" in request.args:
        wallet_ids = (await get_user(g.wallet.user)).wallet_ids
    for game in await get_satoshigo_admin_games(wallet_ids):
        if not game.id:
            return jsonify(), HTTPStatus.OK
        else:
            return (
                jsonify(
                    [
                        players._asdict()
                        for players in await get_satoshigo_players_gameid(game.id)
                    ]
                ),
                HTTPStatus.OK,
            )
    return jsonify(), HTTPStatus.OK