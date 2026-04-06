# Social Media Team Dashboard — Platform API Setup Guide

## Overview
The dashboard is fully functional for content generation without API tokens.
Adding API tokens enables **autonomous publishing** to each platform.

**Priority order:** Facebook + Instagram (one setup) > LinkedIn > TikTok

---

## Step 1: Meta Graph API (Facebook + Instagram)

This single setup covers BOTH Facebook and Instagram for all 3 brands.

### 1.1 Create a Meta Developer App
1. Go to https://developers.facebook.com/
2. Log in with the Facebook account that has admin access to all 3 brand pages
3. Click "My Apps" (top right) > "Create App"
4. Choose "Business" type
5. App name: "Social Media Team Dashboard"
6. Contact email: your business email
7. Business: select your Meta Business account

### 1.2 Add Products
In the app dashboard:
1. Click "Add Product" in the left sidebar
2. Add: **Facebook Login for Business**
3. Add: **Instagram Graph API**

### 1.3 Request Permissions
Go to App Review > Permissions:
- `pages_manage_posts` — publish to Facebook pages
- `pages_read_engagement` — read page metrics
- `instagram_basic` — read IG business account info
- `instagram_content_publish` — publish to Instagram
- `instagram_manage_insights` — read IG metrics

### 1.4 Generate Page Access Tokens
1. Go to https://developers.facebook.com/tools/explorer/
2. Select your app from the dropdown
3. Click "Get Token" > "Get Page Access Token"
4. Grant access to all 3 brand pages
5. For each page, copy the Page Access Token

### 1.5 Extend to Long-Lived Token (60 days)
For each page token, run:
```
GET https://graph.facebook.com/v19.0/oauth/access_token?
  grant_type=fb_exchange_token&
  client_id={APP_ID}&
  client_secret={APP_SECRET}&
  fb_exchange_token={SHORT_LIVED_TOKEN}
```

### 1.6 Get Page IDs
For each brand's Facebook page:
```
GET https://graph.facebook.com/v19.0/me/accounts?access_token={TOKEN}
```
This returns page IDs for all pages you manage.

### 1.7 Get Instagram Business Account IDs
For each page:
```
GET https://graph.facebook.com/v19.0/{PAGE_ID}?fields=instagram_business_account&access_token={TOKEN}
```

### 1.8 Add to Dashboard
Go to http://localhost:5001/settings or add to .env:
```
# Nova - Facebook
NOVA_FB_PAGE_ID={nova_page_id}
NOVA_FB_ACCESS_TOKEN={nova_long_lived_token}

# Nova - Instagram (uses same token, different page_id)
NOVA_IG_BUSINESS_ID={nova_ig_business_id}
NOVA_IG_ACCESS_TOKEN={nova_long_lived_token}

# Briarwood - Facebook
BWD_FB_PAGE_ID={bwd_page_id}
BWD_FB_ACCESS_TOKEN={bwd_long_lived_token}

# Briarwood - Instagram
BWD_IG_BUSINESS_ID={bwd_ig_business_id}
BWD_IG_ACCESS_TOKEN={bwd_long_lived_token}

# Eudaimonia - Facebook
ERH_FB_PAGE_ID={erh_page_id}
ERH_FB_ACCESS_TOKEN={erh_long_lived_token}

# Eudaimonia - Instagram
ERH_IG_BUSINESS_ID={erh_ig_business_id}
ERH_IG_ACCESS_TOKEN={erh_long_lived_token}
```

### Token Refresh
Long-lived tokens expire after 60 days. Set a reminder to refresh them.
The dashboard will show "Token Expired" in Settings when this happens.

---

## Step 2: LinkedIn API

### 2.1 Create a LinkedIn App
1. Go to https://www.linkedin.com/developers/
2. Click "Create App"
3. App name: "Social Media Team"
4. LinkedIn Page: select your company page
5. App logo: upload Nova logo or generic
6. Complete verification

### 2.2 Request Products
In the app settings > Products tab:
- Request: **Share on LinkedIn** (w_member_social)
- Request: **Marketing Developer Platform** (for organization posts)

### 2.3 Generate Access Token
1. Go to the Auth tab
2. Copy Client ID and Client Secret
3. Use the OAuth 2.0 flow to get an access token

Quick token via LinkedIn Token Generator:
```
https://www.linkedin.com/developers/tools/oauth/token-generator
```
Select scopes: `w_member_social`, `w_organization_social`

### 2.4 Get Organization IDs
```
GET https://api.linkedin.com/v2/organizationalEntityAcls?q=roleAssignee
Authorization: Bearer {TOKEN}
```

### 2.5 Add to Dashboard .env
```
NOVA_LI_ACCESS_TOKEN={token}
NOVA_LI_ORG_ID={org_id}
BWD_LI_ACCESS_TOKEN={token}
BWD_LI_ORG_ID={org_id}
ERH_LI_ACCESS_TOKEN={token}
ERH_LI_ORG_ID={org_id}
```

---

## Step 3: TikTok API

### 3.1 Create a TikTok Developer App
1. Go to https://developers.tiktok.com/
2. Register/login
3. Create app > Select "Content Posting API"
4. Complete app review (takes 1-3 business days)

### 3.2 Request Scopes
- `video.publish` — post videos
- `video.upload` — upload video content

### 3.3 Generate Access Token
Use the OAuth 2.0 flow per TikTok's documentation.
Note: TikTok requires video content — static images are not supported.

### 3.4 Add to Dashboard .env
```
NOVA_TT_ACCESS_TOKEN={token}
BWD_TT_ACCESS_TOKEN={token}
ERH_TT_ACCESS_TOKEN={token}
```

---

## Without API Tokens

The dashboard works perfectly without tokens:
- Agents generate calendars, captions, image prompts, and review content
- Posts show in the dashboard as "approved" and ready to copy-paste
- You manually publish from the Posts page

**This is the recommended starting mode** — let the agents generate content for a week, review quality, then connect APIs once you trust the output.

---

## Running the Dashboard

```bash
cd "C:/Users/ktnsh/Recovered Project/techn/social-media-dashboard"
C:\Users\ktnsh\AppData\Local\Programs\Python\Python312\python.exe app.py
```

Dashboard: http://localhost:5001
