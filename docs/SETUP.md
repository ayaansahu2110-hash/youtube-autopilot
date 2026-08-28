# One-time setup

The code can run unattended in GitHub Actions, but three external services require account-owner authorization once.

## 1. OpenAI API

A ChatGPT subscription and API billing are separate. Create an OpenAI API key and keep it private. Later add it to the GitHub repository as an Actions secret named `OPENAI_API_KEY`.

## 2. Pexels (recommended, free)

Create a Pexels account, request an API key, and add it as the GitHub Actions secret `PEXELS_API_KEY`. If you skip this, the renderer still works but uses a simple fallback background instead of stock clips.

## 3. Google / YouTube APIs

In Google Cloud Console:

1. Create a project for YouTube Autopilot.
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Configure the OAuth consent screen. If the app is in testing, add the Google account that owns your YouTube channel as a test user.
4. Create an OAuth client ID of type **Desktop app**.
5. Download the JSON file and save it locally as `secrets/client_secret.json`. Never commit it.

Then on your Windows PC, from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m autopilot.cli doctor
python -m autopilot.cli auth-youtube
```

A Google browser page will open. Sign in with the channel-owner Google account and approve the requested YouTube upload/read-only analytics permissions. The program writes `secrets/youtube_token.json` locally.

## 4. Add OAuth files to GitHub Secrets safely

Do **not** upload the JSON files to the repository. Encode each locally and copy the encoded value to GitHub Actions secrets:

```powershell
.\scripts\encode_secret.ps1 secrets\client_secret.json
```

Paste the clipboard value into a repository secret named `YOUTUBE_CLIENT_SECRETS_B64`.

Then:

```powershell
.\scripts\encode_secret.ps1 secrets\youtube_token.json
```

Paste that into a repository secret named `YOUTUBE_TOKEN_B64`.

The repository should then have these four Actions secrets:

- `OPENAI_API_KEY`
- `PEXELS_API_KEY` (recommended)
- `YOUTUBE_CLIENT_SECRETS_B64`
- `YOUTUBE_TOKEN_B64`

## 5. First safe cloud test

The daily workflow defaults to `private` uploads. Open the **Actions** tab, choose **Daily YouTube Autopilot**, and use **Run workflow** once. Review the private video in YouTube Studio before allowing any broader visibility.

New unverified YouTube API projects can be restricted to private uploads until Google completes the required API compliance audit. Do not set public mode as a workaround.

## 6. Later: public publishing

After you are satisfied with several private test videos and your Google API project/channel is permitted to publish as intended, set repository variables:

- `UPLOAD_PRIVACY_STATUS=public`
- `ALLOW_PUBLIC_UPLOADS=true`

Until both are set, the code refuses public publishing.
