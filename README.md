# 🎯 BC Loyalty Bot

A unified Telegram bot system for managing and displaying promotional content with complete stateless operation. Content managers can create, edit, and publish promos through a natural Telegram interface, while users browse them with intuitive navigation. All user sessions are stateless - no server-side storage required.

## ✨ Key Features

### Unified Bot Experience
- **Single Bot Interface**: One bot handles both user browsing and admin management
- **Stateless Design**: No session storage - all state embedded in callback data
- **Persistent Navigation**: Users can return months later and continue from where they left
- **Role-Based Access**: Automatic admin detection with enhanced controls

### User Features
- **Promo Carousel**: Navigate through active promotions with ← → buttons
- **Smart Layout**: Text + image + link button in a single message
- **In-Place Navigation**: Messages update without creating new ones
- **Instant Access**: Visit promotional links with one click

### Admin Features
- **Natural Content Creation**: Send regular Telegram messages (text + image + link)
- **Live Management**: Edit, toggle, and delete promos with inline buttons
- **Flexible Publishing**: Publish immediately or save as draft
- **Command Interface**: Quick actions via `/list`, `/toggle`, `/delete` commands

### Technical Highlights
- **Google Sheets Backend**: No database required, direct spreadsheet editing
- **Telegram File Storage**: Images stored using Telegram's infrastructure (free!)
- **Stateless Callbacks**: All navigation state encoded in button data
- **Order Management**: Simple numeric ordering with easy insertion
- **Real-time Sync**: Content refreshes automatically every 5 minutes

## 🚀 Quick Start

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Name: `BC Loyalty Bot`
3. Username: `BCloyaltybot` (or your preferred name)
4. Save token → `MAIN_BOT_TOKEN`

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
1 | "🎉 Welcome to BC Loyalty! Get 20% off your first order!" | "" | "https://bc.com/welcome" | 10 | "active" | "admin" | "2024-01-01"

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
MAIN_BOT_TOKEN=123456789:ABC-your-bot-token
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account","project_id":"..."}
GOOGLE_SPREADSHEET_ID=1ABC...XYZ
HEROKU_APP_NAME=your-app-name
```

**Deploy:**
```bash
git clone your-repo
cd bc-loyalty-bot
heroku create bc-loyalty-bot
heroku config:set MAIN_BOT_TOKEN="your_token"
heroku config:set GOOGLE_SHEETS_CREDENTIALS='{"type":"service_account",...}'
heroku config:set GOOGLE_SPREADSHEET_ID="your_id"
heroku config:set HEROKU_APP_NAME="bc-loyalty-bot"
git push heroku main
heroku ps:scale web=1
```

## 📖 Usage Guide

### For Content Managers (Admins)

**Creating New Promo:**
1. Send a regular message to the bot with:
   - Promo text (required)
   - Image (optional) 
   - Link anywhere in text (optional)
2. Bot shows live preview with buttons:
   - 📤 **Publish** (sets status to "active")
   - 📄 **Draft** (saves for later)
   - 📝 **Edit** (modify before saving)
   - ❌ **Cancel** (discard)

**Managing Existing Promos:**
```bash
/list                 # View all promos with management buttons
/toggle 5            # Toggle promo ID 5 (active ↔ inactive)
/delete 5            # Delete promo ID 5
/edit 5              # Edit promo ID 5 (then send new content)
```

**Inline Management:**
- Navigate to any promo as admin
- Use admin buttons: 📋 List | 📝 Edit | 🔄 Toggle | 🗑️ Delete
- All actions update in-place with status messages

**Google Sheets Direct Editing:**
- Edit spreadsheet for bulk changes
- Reorder promos by changing order numbers
- Bot syncs automatically every 5 minutes

### For Users

**Main Bot Interface:**
1. Send `/start` to begin
2. Browse promos with ← → buttons  
3. Click 🔗 Visit Link to access offers
4. Content updates automatically
5. Return anytime - your place is remembered

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Single Bot    │    │  Google Sheets   │    │  Stateless      │
│   (Unified)     │◄──►│   (Database)     │    │  Callbacks      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Role Detection  │    │ Real-time Sync   │    │ Embedded State  │
│ Admin/User UI   │    │ 5min Cache       │    │ No Sessions     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Key Components:**
- **Unified Interface**: Single bot with role-based feature access
- **Stateless Operation**: All navigation state embedded in callback data
- **Google Sheets**: Simple database with direct editing capability
- **Telegram File Storage**: Free image hosting using Telegram's infrastructure
- **Cache System**: Optimized performance with periodic refresh
- **Persistent State**: Users can return anytime without losing position

## 🔧 Technical Implementation

### File Structure
```
bc-loyalty-bot/
├── app.py                 # Main entry point (Heroku)
├── bot.py                 # Bot application setup and routing
├── user_handlers.py       # User interface and navigation
├── admin_handlers.py      # Admin management functions
├── content_manager.py     # Google Sheets integration
├── auth.py               # Authentication and authorization
├── utils.py              # Stateless utilities and helpers
├── requirements.txt      # Python dependencies
├── Procfile             # Heroku configuration
├── .python-version      # Python version
└── README.md           # This file
```

### Stateless Design Principles

**Callback Data Encoding:**
```python
# Simple format: action_key1_value1_key2_value2
"next_idx_2_ts_1722176789"

# JSON format for complex state:
"state_{'a':'admin_edit','promo_id':5,'idx':2,'ts':1722176789}"
```

**State Validation:**
- Timestamps prevent stale callback execution
- All user context embedded in button data
- No server-side session storage required

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

### Bot Commands
| Command | Access | Description | Example |
|---------|--------|-------------|---------|
| `/start` | All | Start bot and show promos | `/start` |
| `/list` | Admin | View all promos with buttons | `/list` |
| `/toggle {id}` | Admin | Toggle promo status | `/toggle 5` |
| `/delete {id}` | Admin | Delete promo | `/delete 5` |
| `/edit {id}` | Admin | Edit promo content | `/edit 5` |

### Status Values
| Status | Description | Visible to Users |
|--------|-------------|------------------|
| `active` | Published and live | ✅ Yes |
| `draft` | Work in progress | ❌ No |
| `inactive` | Hidden but preserved | ❌ No |

### Order System
- **Default increment**: +10 (10, 20, 30, 40...)
- **Easy insertion**: Add 15 between 10 and 20
- **Custom ordering**: Edit order field in Google Sheets
- **Lower numbers appear first**

## 🔍 Troubleshooting

### Common Issues

**"Access Denied" Error**
- Check if user_id/username is in authorized_users sheet
- Verify phone number format: `"+1234567890"` (with quotes)
- Ensure Google Sheets has service account access

**Images Not Displaying**
- Ensure images uploaded through Telegram (not external URLs)
- Check if file_id is properly stored in sheets
- Verify image file size under Telegram limits (20MB)

**Bot Not Responding**
```bash
heroku logs --tail    # Check for errors
heroku ps            # Verify web dyno is running
heroku restart       # Restart if needed
```

**Callback Expired Messages**
- Normal behavior for old buttons (>1 hour)
- Users should use `/start` to refresh
- Consider reducing callback timeout if too aggressive

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

# Scale web dyno
heroku ps:scale web=1
```

## 🔐 Security & Privacy

### Stateless Compliance
- **No Personal Data Storage**: All user state in callback data only
- **Session-Free**: Compliant with data protection regulations
- **Temporary State**: Callback data expires automatically
- **No Tracking**: No persistent user behavior storage

### Access Control
- **Admin Authorization**: User ID/username matching in Google Sheets
- **Service Account**: Limited Google Sheets access only
- **Environment Variables**: Sensitive data stored securely
- **Callback Validation**: Timestamped to prevent replay attacks

### Best Practices
- Store phone numbers in quotes: `"+1234567890"`
- Use strong, unique bot tokens
- Limit service account permissions to specific spreadsheet
- Regularly review authorized users list
- Monitor logs for suspicious activity

## 💰 Cost Analysis

### Heroku Hosting
- **Eco Dyno**: $5/month (sleeps after 30min inactivity)
- **Basic Dyno**: $7/month (always on, recommended)

### Google Services
- **Google Sheets API**: Free (100 requests/100 seconds)
- **Google Drive Storage**: Free (15GB limit)

### Telegram
- **Bot API**: Completely free
- **File Storage**: Free (20MB per file, 1.5GB total per bot)

**Total Monthly Cost: $5-7** (Heroku hosting only)

## 🚀 Deployment Options

### Heroku (Current)
- Webhook-based operation
- Environment variable management
- Automatic HTTPS
- Easy scaling

### Alternative Platforms
- **Railway**: Similar to Heroku, competitive pricing
- **Render**: Free tier available
- **DigitalOcean App Platform**: $5/month
- **Google Cloud Run**: Pay-per-use model

## 📈 Future Enhancements

### Planned Features
- **Scheduling**: Auto-publish promos at specific times
- **Analytics**: Track promo views and link clicks
- **Rich Media**: Video and document support
- **Bulk Operations**: CSV import/export for promos
- **User Preferences**: Language and notification settings

### Technical Improvements
- **Callback Compression**: More efficient state encoding
- **Cache Optimization**: Smarter refresh strategies
- **Error Recovery**: Better handling of edge cases
- **Performance Metrics**: Response time monitoring

## 🤝 Contributing

### Development Setup
```bash
git clone your-repo
cd bc-loyalty-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your tokens
python app.py
```

### Testing Stateless Design
```python
# Test callback data encoding/decoding
from utils import encode_callback_state, StateManager.decode_callback_data

# Encode state
callback_data = encode_callback_state("next", idx=2, admin=True, ts=1722176789)

# Decode state  
action, state = StateManager.decode_callback_data(callback_data)
print(f"Action: {action}, State: {state}")
```

### Code Style
- Use double quotes for strings: `"text"`
- Stateless design principles throughout
- Comprehensive logging for debugging
- Error handling for all external API calls

## 📄 License

MIT License - Feel free to modify and distribute.

## 🆘 Support

### Getting Help
1. Check logs: `heroku logs --tail`
2. Verify Google Sheets setup and permissions
3. Test bot token with Telegram API
4. Review callback data encoding/decoding

### Useful Resources
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Google Sheets API](https://developers.google.com/sheets/api)
- [Heroku Documentation](https://devcenter.heroku.com/)
- [python-telegram-bot Library](https://python-telegram-bot.readthedocs.io/)

---

**Ready to launch your stateless loyalty program? Deploy BC Loyalty Bot and start engaging customers with persistent, manageable promotional content!** 🎉