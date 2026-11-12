"""The /alerts endpoints: channel settings, test alerts, and keeping secrets secret."""

import pytest

DISCORD = "https://discord.com/api/webhooks/123456/secret_WEBHOOK-value"
TOKEN = "123456789:" + "S" * 35


def channels(client):
    return {c["name"]: c["source"] for c in client.get("/alerts/channels").json()}


@pytest.mark.parametrize(
    "url",
    ["", "http://discord.com/api/webhooks/1/abc", "https://discord.com.evil.example/api/webhooks/1/abc",
     "https://evil.example/https://discord.com/api/webhooks/1/abc", "https://discord.com/api/webhooks/1/a/../../x",
     "https://discord.com/api/webhooks/1/abc?x=1", "https://user@discord.com/api/webhooks/1/abc"],
)
def test_only_real_discord_webhooks_are_accepted(logged_in, url):
    response = logged_in.put("/alerts/channels/discord", json={"webhookUrl": url})
    assert response.status_code == 400
    assert "evil" not in response.text and "user@" not in response.text


@pytest.mark.parametrize(
    ("token", "chat"),
    [("short:abc", "1"), (TOKEN + "/../x", "1"), (TOKEN, "1; drop"), ("", "")],
)
def test_bad_telegram_settings_are_refused(logged_in, token, chat):
    assert logged_in.put("/alerts/channels/telegram", json={"botToken": token, "chatId": chat}).status_code == 400


def test_saved_channels_are_used_at_once_and_never_shown(logged_in, sent):
    assert channels(logged_in) == {"discord": None, "telegram": None}
    assert logged_in.post("/alerts/test").status_code == 400  # nothing set up yet

    logged_in.put("/alerts/channels/discord", json={"webhookUrl": DISCORD})
    logged_in.put("/alerts/channels/telegram", json={"botToken": TOKEN, "chatId": "-100123"})
    assert channels(logged_in) == {"discord": "dashboard", "telegram": "dashboard"}

    results = logged_in.post("/alerts/test").json()
    assert {r["channel"]: r["ok"] for r in results} == {"discord": True, "telegram": True}
    urls = {url for url, _ in sent.posts}
    assert urls == {DISCORD, f"https://api.telegram.org/bot{TOKEN}/sendMessage"}

    everything = "".join(logged_in.get(p).text for p in ["/alerts/channels", "/alerts", "/monitors"])
    assert "secret_WEBHOOK" not in everything and TOKEN not in everything


def test_removing_falls_back_to_env(logged_in, override_settings, sent):
    override_settings(telegram_bot_token=TOKEN, telegram_chat_id="111")
    assert channels(logged_in)["telegram"] == "env"
    assert logged_in.delete("/alerts/channels/telegram").status_code == 404  # .env can't be removed here

    logged_in.put("/alerts/channels/telegram", json={"botToken": TOKEN, "chatId": "222"})
    logged_in.post("/alerts/test")
    assert sent.posts[-1][1]["chat_id"] == "222"  # the dashboard wins

    assert logged_in.delete("/alerts/channels/telegram").status_code == 200
    logged_in.post("/alerts/test")
    assert sent.posts[-1][1]["chat_id"] == "111"


def test_test_alerts_are_rate_limited(logged_in):
    logged_in.put("/alerts/channels/discord", json={"webhookUrl": DISCORD})
    codes = [logged_in.post("/alerts/test").status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_discord_mentions_are_switched_off(logged_in, sent):
    logged_in.put("/alerts/channels/discord", json={"webhookUrl": DISCORD})
    logged_in.post("/alerts/test")
    assert sent.posts[0][1]["allowed_mentions"] == {"parse": []}
