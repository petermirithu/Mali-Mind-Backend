# Firebase Setup for Production (Vercel)

This guide explains how to configure Firebase for production deployment on Vercel.

## Overview

The Firebase configuration in [firebase/config.py](firebase/config.py) supports:
- **All environments**: Reads `FIREBASE_SERVICE_ACCOUNT_JSON` through the case-insensitive settings loader. Existing lowercase variable names also work.
- **Local development**: Falls back to the untracked `firebase/firebase-service-account.json` when no JSON environment value is configured.
- **Production**: `VERCEL=1`, `APP_ENV=prod`, or `APP_ENV=production` requires the JSON environment value; there is no file fallback.

This approach allows you to:
1. Keep sensitive credentials out of Git
2. Store them securely in Vercel's environment variables
3. Maintain a local development setup without secrets

## Setup Steps

### Step 1: Get Your Firebase Service Account JSON

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project
3. Click **Project Settings** (gear icon)
4. Go to **Service Accounts** tab
5. Click **Generate New Private Key**
6. This downloads a JSON file (keep it safe!)

### Step 2: Prepare the JSON for Environment Variable

The JSON file contains sensitive credentials. You need to convert it to a single-line string:

#### Option A: Using Command Line

```bash
# On macOS/Linux:
cat firebase/firebase-service-account.json | jq -r tostring | pbcopy

# On Windows (PowerShell):
$json = Get-Content firebase/firebase-service-account.json | ConvertFrom-Json | ConvertTo-Json -Compress
$json | Set-Clipboard
```

#### Option B: Manual Copy-Paste (for Vercel Dashboard)

1. Open `firebase/firebase-service-account.json` in your editor
2. Select **all** the content (Cmd+A / Ctrl+A)
3. Copy it (Cmd+C / Ctrl+C)

### Step 3: Set Environment Variable in Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Select the Vercel project connected to `Mali-Mind-Backend`.
3. Click **Settings** → **Environment Variables**
4. Click **Add New**
5. Fill in:
   - **Name**: `FIREBASE_SERVICE_ACCOUNT_JSON`
   - **Value**: Paste the entire JSON object (from Step 2), without wrapping it in extra quotes.
   - **Environment**: Configure both **Production** and **Preview**, using separate Firebase projects where appropriate.
6. Click **Save**

### Step 4: Verify Environment Variable

After setting it in Vercel:

1. Go to **Deployments** 
2. Start a new deployment (or wait for automatic deploy on git push)
3. Once deployed, check the logs

**Test Firebase Configuration:**

```bash
# Add a test endpoint to your API (or use existing auth endpoint)
# If Firebase initializes correctly, you won't see "FileNotFoundError"
```

## How It Works

### Development Environment

When not running on Vercel and `APP_ENV` is neither `prod` nor `production`, a missing JSON setting falls back to the local credential file. A configured JSON value always takes priority.

### Production Environment (Vercel)

Set `APP_ENV=production` and `FIREBASE_SERVICE_ACCOUNT_JSON`. The case-insensitive settings loader supplies the JSON to Firebase Admin, independent of the environment-variable spelling. `VERCEL=1` also enforces environment-only credentials in previews. Initialization happens during import, so invalid or missing credentials prevent the application from starting rather than leaving broken authentication routes.

## Troubleshooting

### Issue: "Firebase service account JSON not found in environment variable"

**Solution**: 
- Set `FIREBASE_SERVICE_ACCOUNT_JSON` (legacy lowercase names also work).
- Check that it is set for the deployment's **Production** or **Preview** scope.
- Redeploy after adding the variable

### Issue: "Invalid JSON in firebase_service_account_json"

**Possible causes**:
1. JSON wasn't pasted completely
2. Extra quotes were added during copy-paste
3. JSON was modified or corrupted

**Solution**:
1. Delete the environment variable in Vercel
2. Copy the JSON again from your local file (Steps 2-3)
3. Re-add the environment variable and redeploy

### Issue: "FileNotFoundError" in development

**Solution**:
- Ensure `firebase/firebase-service-account.json` exists locally
- Keep the credential file ignored by Git. Never commit it, including for development.
- Alternatively, set `FIREBASE_SERVICE_ACCOUNT_JSON` in the ignored local `.env` file.

## Security Best Practices

1. **Never commit the JSON file to Git**
   - Already configured in `.gitignore`

2. **Rotate service account keys regularly**
   - Firebase Console → Service Accounts → Manage keys

3. **Limit permissions**
   - Use a dedicated Firebase service account with minimal permissions
   - Don't use your main Firebase admin account

4. **Environment variable scope**
   - Configure JSON credentials separately for **Production** and **Preview**.
   - Use a separate Firebase project for staging tests; local development may use an ignored credential file.

5. **Monitor Firebase usage**
   - Check Firebase Console for unexpected authentication attempts
   - Set up billing alerts

## Testing Firebase Connection

To verify Firebase is working after deployment:

```python
# In your API, test with:
from firebase.config import verify_firebase_token

# Try verifying a valid token from your frontend
# If it works without errors, Firebase is initialized correctly
```

## Switching Environments

### To use a different Firebase project for production:

1. Get the new Firebase service account JSON
2. Follow Steps 1-3 above
3. Redeploy to Vercel

### Missing Firebase credentials

Firebase is required by the authentication API. Removing production credentials intentionally fails startup. Restore valid configuration and redeploy; do not suppress initialization errors or commit a private key as a workaround.

## Reference

- [Firebase Admin SDK for Python](https://firebase.google.com/docs/admin/setup)
- [Vercel Environment Variables](https://vercel.com/docs/projects/environment-variables)
- [Firebase Service Accounts](https://firebase.google.com/docs/admin/setup#service-accounts)

---

**Status**: Local regression checks pass. Verify the deployed application with a real Firebase ID token before enabling production traffic. See the [deployment checklist](VERCEL_DEPLOYMENT.md#deployment-checklist).
