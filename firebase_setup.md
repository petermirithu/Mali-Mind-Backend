# Firebase Setup for Production (Vercel)

This guide explains how to configure Firebase for production deployment on Vercel.

## Overview

Your Firebase configuration (`firebase/config.py`) now supports:
- **Development**: Loads from local `firebase/firebase-service-account.json` file
- **Production**: Loads from `firebase_service_account_json` environment variable

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
2. Select your project: `enabled-loan-tracker-backend`
3. Click **Settings** → **Environment Variables**
4. Click **Add New**
5. Fill in:
   - **Name**: `firebase_service_account_json`
   - **Value**: Paste the entire JSON content (from Step 2)
   - **Environment**: Select **Production** (and Preview if desired)
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

When `app_env=dev`:
```python
# Loads from local file
cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
# SERVICE_ACCOUNT_PATH = "firebase/firebase-service-account.json"
```

### Production Environment (Vercel)

When `app_env=prod`:
```python
# Loads from environment variable
firebase_json_str = os.environ.get("firebase_service_account_json")
firebase_json_dict = json.loads(firebase_json_str)
cred = credentials.Certificate(firebase_json_dict)
```

## Troubleshooting

### Issue: "Firebase service account JSON not found in environment variable"

**Solution**: 
- Verify the environment variable name is exactly: `firebase_service_account_json`
- Check that it's set to **Production** scope in Vercel
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
- File should not be in `.gitignore` (it is safe to commit if needed for dev)
- Or, add to `.env` file: `app_env=dev`

## Security Best Practices

1. **Never commit the JSON file to Git**
   - Already configured in `.gitignore`

2. **Rotate service account keys regularly**
   - Firebase Console → Service Accounts → Manage keys

3. **Limit permissions**
   - Use a dedicated Firebase service account with minimal permissions
   - Don't use your main Firebase admin account

4. **Environment variable scope**
   - Set `firebase_service_account_json` only for **Production**
   - Keep development using local file

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

### To disable Firebase temporarily:

1. Remove `firebase_service_account_json` from environment variables
2. Make sure your code handles missing Firebase gracefully
3. Consider wrapping Firebase imports in try-catch blocks

## Reference

- [Firebase Admin SDK for Python](https://firebase.google.com/docs/admin/setup)
- [Vercel Environment Variables](https://vercel.com/docs/projects/environment-variables)
- [Firebase Service Accounts](https://firebase.google.com/docs/admin/setup#service-accounts)

---

**Status**: ✅ Ready for Production
**Last Updated**: August 2024
