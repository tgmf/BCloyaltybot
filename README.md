# 🎯 BC Loyalty Bot

A dual-bot Telegram system for managing and displaying promotional content. Content managers can easily create, edit, and publish promos through a natural Telegram interface, while users browse them with intuitive navigation.

## ✨ Features

### Main Bot (@BCloyaltybot)
- **Promo Carousel**: Navigate through active promotions with ← → buttons
- **Smart Layout**: Text + image + link button in a single message
- **In-Place Navigation**: Messages update without creating new ones
- **Instant Updates**: Content refreshes automatically every 5 minutes

### Admin Bot (@BCloyaltyadminbot)
- **Natural Content Creation**: Just send a regular Telegram message (text + image + link)
- **Live Preview**: See exactly how content will appear to users
- **Flexible Publishing**: Publish immediately, save as draft, or schedule
- **Easy Management**: Edit, toggle, and delete existing promos
- **Authorization System**: Secure access control via user ID/username

### Content Management
- **Google Sheets Backend**: No database required, edit content directly in spreadsheet
- **Telegram File Storage**: Images stored using Telegram's file system (free!)
- **Order Management**: Simple numeric ordering with easy insertion (+10 increments)
- **Status Control**: Active, draft, and inactive states

## 🚀 Quick Start

### 1. Create Telegram Bots

**Main Bot:**
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Name: `BC Loyalty Bot`
3. Username: `BCloyaltybot`
4. Save token → `MAIN_BOT_TOKEN`

**Admin Bot:**
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Name: `BC Loyalty Admin`
3. Username: `BCloyaltyadminbot`
4. Save token → `ADMIN_BOT_TOKEN`

### 2. Setup Google Sheets

**Create Spreadsheet:**
1. Go to [Google Sheets](https://sheets.google.com)
2. Create new spreadsheet: "BC Loyalty Bot Content"
3. Copy spreadsheet ID from URL

**Sheet 1: "promo_messages"**
```
A: id | B: text | C: image_file_id | D: link | E: order | F: status | G: created_by | H: created_at
```

**Sheet 2: "authorized_users"**
```
A: phone_number | B: user_id | C: username | D: added_at
```

**Sample Data:**
```
Sheet: promo_messages
1 | "Welcome to BC Loyalty!" | "" | "https://bc.com" | 10 | "active" | "admin" | "2024-01-01"

Sheet: authorized_users  
"+1234567890" | "123456789" | "admin_user" | "2024-01-01"
```

### 3. Google Cloud Setup

1. **Enable API**: [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
2. **Create Service Account**: IAM & Admin → Service Accounts → Create
3. **Generate Key**: Actions → Create Key → JSON
4. **Share Spreadsheet**: Add service account email with Editor access

### 4. Deploy to Heroku

**Environment Variables:**
```bash
MAIN_BOT_TOKEN=123456789:ABC-your-main-bot-token
ADMIN_BOT_TOKEN=987654321:XYZ-your-admin-bot-token
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account","project_id":"..."}
GOOGLE_SPREADSHEET_ID=1ABC...XYZ
```

**Deploy:**
```bash
git clone your-repo
cd bc-loyalty-bot
heroku create bc-loyalty-bot
heroku config:set MAIN_BOT_TOKEN="your_token"
heroku config:set ADMIN_BOT_TOKEN="your_token"
heroku config:set GOOGLE_SHEETS_CREDENTIALS='{"type":"service_account",...}'
heroku config:set GOOGLE_SPREADSHEET_ID="your_id"
git push heroku main
heroku ps:scale worker=1
```

## 📖 Usage Guide

### For Content Managers

**Creating New Promo:**
1. Open admin bot (@BCloyaltyadminbot)
2. Send regular message with:
   - Promo text
   - Image (optional)
   - Link anywhere in text
3. Choose: 📤 Publish | 📝 Edit | 📄 Draft
4. Optionally specify order number

**Managing Existing Promos:**
```
/list                 # View all promos with buttons
/toggle 5            # Toggle promo ID 5 (active ↔ inactive)
/delete 5            # Delete promo ID 5
```

**Google Sheets Direct Editing:**
- Edit spreadsheet for bulk changes
- Reorder promos by changing order numbers
- Bot syncs automatically every 5 minutes

### For Users

**Main Bot (@BCloyaltybot):**
1. Send `/start`
2. Browse promos with ← → buttons
3. Click 🔗 Visit Link to access offers
4. Content updates automatically

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Admin Bot     │    │  Google Sheets   │    │    Main Bot     │
│  (Content Mgmt) │◄──►│   (Database)     │◄──►│ (User Interface)│
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Natural Message │    │ Real-time Sync   │    │ Carousel UI     │
│ Composition     │    │ 5min Cache       │    │ In-place Update │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Key Components:**
- **Dual Bot System**: Separate concerns for management vs. user experience
- **Google Sheets**: Acts as simple database with direct editing capability
- **Telegram File Storage**: Free image hosting using Telegram's infrastructure
- **Cache System**: Optimized performance with periodic refresh
- **In-Memory Sessions**: User navigation state tracking

## 🔧 Technical Details

### File Structure
```
bc-loyalty-bot/
├── loyalty_bot.py          # Main application
├── requirements.txt        # Python dependencies
├── Procfile               # Heroku configuration
├── .python-version        # Python version for Heroku
├── .env.example           # Environment template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

### Dependencies
- `python-telegram-bot==20.7` - Telegram Bot API
- `gspread==5.12.0` - Google Sheets integration
- `google-auth==2.23.4` - Google authentication
- `python-dotenv==1.0.0` - Environment variables

### Data Models

**Promo Message:**
```json
{
  "id": 1,
  "text": "Promotional content text",
  "image_file_id": "telegram_file_id",
  "link": "https://example.com",
  "order": 10,
  "status": "active|draft|inactive",
  "created_by": "user_id",
  "created_at": "2024-01-01T00:00:00"
}
```

**Authorization:**
```json
{
  "phone_number": "+1234567890",
  "user_id": "123456789", 
  "username": "admin_user",
  "added_at": "2024-01-01"
}
```

## 🛠️ Management Commands

### Admin Bot Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Show admin panel | `/start` |
| `/list` | View all promos with edit buttons | `/list` |
| `/toggle {id}` | Toggle promo status | `/toggle 5` |
| `/delete {id}` | Delete promo | `/delete 5` |

### Status Values
| Status | Description | Visible to Users |
|--------|-------------|------------------|
| `active` | Published and live | ✅ Yes |
| `draft` | Work in progress | ❌ No |
| `inactive` | Hidden but preserved | ❌ No |

### Order System
- **Default increment**: +10 (10, 20, 30, 40...)
- **Easy insertion**: Add 15 between 10 and 20
- **Custom ordering**: Type number when publishing
- **Lower numbers appear first**

## 🔍 Troubleshooting

### Common Issues

**"Access Denied" in Admin Bot**
- Check if user_id/username is in authorized_users sheet
- Verify Google Sheets permissions for service account

**Images Not Displaying**
- Ensure images uploaded through Telegram (not external links)
- Check if file_id is properly stored in sheets

**Bot Not Responding**
```bash
heroku logs --tail    # Check for errors
heroku ps            # Verify worker is running
heroku restart       # Restart if needed
```

**Google Sheets Errors**
- Verify service account has Editor access to spreadsheet
- Check if Google Sheets API is enabled
- Validate JSON credentials format

### Debugging Commands
```bash
# View live logs
heroku logs --tail

# Check app status
heroku ps

# View configuration
heroku config

# Restart application
heroku restart

# Scale worker
heroku ps:scale worker=1
```

## 🔐 Security & Authorization

### Access Control
- **Admin authorization**: User ID or username matching in Google Sheets
- **Service account**: Limited Google Sheets access only
- **Environment variables**: Sensitive data stored securely
- **No database**: Reduced attack surface

### Best Practices
- Store phone numbers in quotes: `"+1234567890"`
- Use strong, unique bot tokens
- Limit service account permissions to specific spreadsheet
- Regularly review authorized users list
- Monitor bot logs for suspicious activity

## 💰 Cost Breakdown

### Heroku Hosting
- **Eco Dyno**: $5/month (sleeps after 30min inactivity)
- **Basic Dyno**: $7/month (always on, recommended for production)

### Google Services
- **Google Sheets API**: Free (100 requests/100 seconds)
- **Google Drive storage**: Free (15GB limit)

### Telegram
- **Bot API**: Completely free
- **File storage**: Free (20MB per file, 1.5GB total per bot)

**Total Monthly Cost: $5-7** (Heroku only)

## 🚀 Deployment Options

### Heroku (Recommended)
- One-click deployment
- Automatic scaling
- Built-in monitoring
- Easy environment management

### Alternative Platforms
- **Railway**: Similar to Heroku, competitive pricing
- **Render**: Free tier available
- **DigitalOcean App Platform**: $5/month
- **Google Cloud Run**: Pay-per-use
- **Self-hosted**: VPS with Docker

## 📈 Future Enhancements

### Planned Features
- **Scheduling**: Auto-publish promos at specific times
- **Analytics**: Track views and link clicks
- **User Targeting**: Segment-based promo delivery
- **Rich Media**: Video and document support
- **A/B Testing**: Multiple promo variants
- **Bulk Operations**: CSV import/export

### Integration Possibilities
- **CRM Integration**: Sync with customer data
- **E-commerce**: Direct product links
- **Analytics**: Google Analytics integration
- **Notifications**: Admin alerts for engagement

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test thoroughly
4. Commit: `git commit -m "Add feature description"`
5. Push: `git push origin feature-name`
6. Create Pull Request

### Development Setup
```bash
git clone your-repo
cd bc-loyalty-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your tokens
python loyalty_bot.py
```

## 📄 License

MIT License - Feel free to modify and distribute.

## 🆘 Support

### Getting Help
1. Check this README for solutions
2. Review Heroku logs: `heroku logs --tail`
3. Verify Google Sheets setup and permissions
4. Test bot tokens with Telegram API

### Useful Links
- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)
- [Google Sheets API Documentation](https://developers.google.com/sheets/api)
- [Heroku Documentation](https://devcenter.heroku.com/)
- [python-telegram-bot Library](https://python-telegram-bot.readthedocs.io/)

---

**Ready to launch your loyalty program? Deploy BC Loyalty Bot and start engaging your customers with beautiful, manageable promotional content!** 🎉