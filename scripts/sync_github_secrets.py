import sys
import json
import base64
import urllib.request
import urllib.error
from nacl import encoding, public

REPO = "Olamideakinade/darkest-minds-shorts"

def encrypt_secret(public_key: str, secret_value: str) -> str:
    public_key_bytes = base64.b64decode(public_key)
    sealed_box = public.SealedBox(public.PublicKey(public_key_bytes))
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

def github_api_request(url: str, token: str, method: str = "GET", data: dict = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "MhieIntelligence-Autopilot-Sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(f"GitHub API Error {e.code}: {err_body}")

def sync_secrets(token: str):
    print(f"🔒 Fetching repository public key for {REPO}...")
    key_info = github_api_request(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", token)
    key_id = key_info["key_id"]
    public_key = key_info["key"]
    print(f"✓ Public key retrieved (Key ID: {key_id})")

    # Load secrets
    with open(".env") as f:
        env_vars = {}
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    with open("data/youtube_token.json") as f:
        youtube_token_str = json.dumps(json.load(f))

    with open("credentials/client_secrets.json") as f:
        client_secrets_str = json.dumps(json.load(f))

    secrets_to_upload = {
        "GEMINI_API_KEY": env_vars.get("GEMINI_API_KEY", ""),
        "TELEGRAM_BOT_TOKEN": env_vars.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_ALLOWED_USER_IDS": env_vars.get("TELEGRAM_ALLOWED_USER_IDS", ""),
        "YOUTUBE_TOKEN_JSON": youtube_token_str,
        "CLIENT_SECRETS_JSON": client_secrets_str,
        "PIXABAY_API_KEY": env_vars.get("PIXABAY_API_KEY", ""),
        "PEXELS_API_KEY": env_vars.get("PEXELS_API_KEY", ""),
    }

    print("\n📦 Uploading encrypted repository secrets...")
    for name, val in secrets_to_upload.items():
        if not val:
            print(f"⚠️ Warning: Value for {name} is empty, skipping.")
            continue
        encrypted_val = encrypt_secret(public_key, val)
        url = f"https://api.github.com/repos/{REPO}/actions/secrets/{name}"
        github_api_request(url, token, method="PUT", data={
            "encrypted_value": encrypted_val,
            "key_id": key_id,
        })
        print(f"  ✓ Secret '{name}' configured successfully.")

    print("\n✓ All secrets synced successfully. Automated uploads remain disabled.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_github_secrets.py <GITHUB_PAT>")
        sys.exit(1)
    pat = sys.argv[1].strip()
    sync_secrets(pat)
