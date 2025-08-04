# 🎯 Your Bot Name

A stateless Telegram bot system for managing promotional content with zero server-side storage. Content managers create and edit promos through natural Telegram interactions, while users browse them with persistent navigation. All user state is embedded in callback data - users can return months later and continue exactly where they left off.

## ✨ Key Features

### Stateless Architecture
- **Zero Session Storage**: All state embedded in callback data
- **Persistent Navigation**: Users return after months to exact same position  
- **Minimal Data Storage**: Only stores admin user_ids (TODO: hash user_ids or implement password-only system)
- **API-Limited Scalability**: Constrained by Telegram and Google API limits, not server memory

### Unified Bot Experience
- **Single Bot Interface**: One bot handles both user browsing and admin management
- **Role-Based UI**: Automatic admin detection with enhanced controls
- **Clean Chat**: Maximum 2 messages in chat (status + current promo)
- **In-Place Updates**: Messages update without creating new ones

### User Features
- **Promo Carousel**: Navigate through promotions with ← → buttons
- **Smart Layout**: Text + image + link button in optimized format
- **Instant Access**: Visit promotional links with one click
- **Persistent Context**: No timeouts or session expiry (TODO: needs extensive testing)

### Admin Features
- **Natural Content Creation**: Send regular Telegram messages (text + image + link)
- **Live Management**: Edit, toggle, and delete promos inline
- **Reply-Based Editing**: Edit by replying to instruction messages
- **Dual View Modes**: Toggle between "active only" and "show all" promos
- **Real-Time Status**: Rich status information with promo details

### Technical Highlights
- **Google Sheets Backend**: Direct spreadsheet editing, no database needed
- **Telegram File Storage**: Images stored using Telegram's infrastructure (free!)
- **Compressed State Encoding**: Base36 + JSON fallback for callback data
- **Auto-Recovery**: Graceful handling of stale callbacks and missing promos
- **Webhook Health Monitoring**: Automatic webhook maintenance in production

## 🚀 Quick Setup

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Name: `Your Bot Name`
3. Username: `yourbotname` (or your choice)
4. Save token → `MAIN_BOT_TOKEN`
5. (Optional) Create dev bot → `DEV_BOT_TOKEN`

### 2. Setup Google Sheets

**Create Spreadsheet:**
1. Go to [Google Sheets](https://sheets.google.com)
2. Create: "Your Bot Content"
3. Copy spreadsheet ID from URL: `1ABC...XYZ`

**Sheet 1: "promo_messages"** (Production)
```
A: id | B: text | C: image_file_id | D: link | E: order | F: status | G: created_by | H: created_at
```

**Sheet 2: "promo_messages_dev"** (Development)
```
A: id | B: text | C: image_file_id | D: link | E: order | F: status | G: created_by | H: created_at
```

**Sheet 3: "authorized_users"**
```
A: admin_id | B: user_id | C: added_at
```

**Sample Data:**
```
Sheet: promo_messages
1 | "🎉 Welcome! Get 20% off your first order!" | "" | "https://example.com/welcome" | 10 | "active" | "123456789" | "2024-01-01"

Sheet: authorized_users  
1 | "123456789" | "2024-01-01"
```

### 3. Google Cloud Setup

1. **Enable API**: [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
2. **Create Service Account**: IAM & Admin → Service Accounts → Create
3. **Generate Key**: Actions → Create Key → JSON
4. **Share Spreadsheet**: Add service account email with Editor access

### 4. Deploy to Heroku

**Environment Variables:**
```bash
MAIN_BOT_TOKEN=123456789:ABC-your-production-bot-token
DEV_BOT_TOKEN=987654321:XYZ-your-development-bot-token  # Optional
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account","project_id":"..."}
GOOGLE_SPREADSHEET_ID=1ABC...XYZ
HEROKU_APP_NAME=your-app-name
DEFAULT_IMAGE_FILE_ID=AgACAgIAAxkBAAI...  # Optional default image
```

**Deploy:**
```bash
git clone your-repo
cd your-bot-folder
heroku create your-bot-name
heroku config:set MAIN_BOT_TOKEN="your_token"
heroku config:set GOOGLE_SHEETS_CREDENTIALS='{"type":"service_account",...}'
heroku config:set GOOGLE_SPREADSHEET_ID="your_id"
heroku config:set HEROKU_APP_NAME="your-bot-name"
git push heroku main
heroku ps:scale web=1
```

## 📖 Usage Guide

### For Users

**Simple Navigation:**
1. Send `/start` → Browse first promo
2. Use ← → buttons to navigate
3. Click 🔗 to visit promotional links
4. Return anytime - your position is preserved

### For Admins

**Adding New Promos:**
1. Send message with text, image (optional), and link (optional)
2. Bot shows preview with options:
   - 🟢 **Publish** (make active immediately)
   - ✏️ **Edit** (modify before publishing)
   - ← **Back** (return to current promo)
   - 🗑️ **Delete** (remove draft)

**Managing Existing Promos:**
- **Navigate**: Use ← → like regular users
- **Toggle View**: 👁️ button switches "Active Only" ↔ "All Promos"
- **Toggle Status**: 🟢/🔴 button activates/deactivates current promo
- **Edit**: ✏️ button shows edit menu
- **Delete**: 🗑️ button with confirmation

**Editing Promos:**
1. Click ✏️ Edit on any promo
2. Choose what to edit:
   - 📝 **Text Only**
   - 🔗 **Link Only** 
   - 🖼️ **Image Only**
   - 🔄 **Replace All**
3. Bot shows instruction message
4. **Reply to instruction** with new content
5. Changes apply immediately

**Pro Tips:**
- Bot automatically extracts links from text
- Supports any image format/size (Telegram limits apply)
- Order numbers control promo sequence (lower = first)
- Edit Google Sheets directly for bulk changes

### Google Sheets Direct Editing

**Reorder Promos**: Change order column values
**Bulk Status Changes**: Edit status column (active/inactive/draft)
**Text Corrections**: Edit text column directly
**Link Updates**: Edit link column

*Bot syncs automatically every 10 minutes or when cache refresh is triggered*

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
│ Dynamic UI      │    │ 10min Cache      │    │ No Sessions     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Core Principles:**
- **Stateless Operation**: All navigation state in callback data
- **Persistent Context**: Users can return after months
- **Unified Interface**: Single bot with role-based features
- **Clean UX**: Maximum 2 messages in chat at any time
- **Real-time Sync**: Content updates across all users instantly

## 🔧 Technical Implementation

### File Structure
```
bc-loyalty-bot/
├── app.py                 # Main entry point (Heroku/local)
├── bot.py                 # Bot application setup and routing
├── user_handlers.py       # User interface and navigation
├── admin_handlers.py      # Admin management functions  
├── content_manager.py     # Google Sheets integration
├── auth.py               # Authentication and authorization
├── state_manager.py      # Stateless state management
├── keyboard_builder.py   # Dynamic keyboard generation
├── utils.py              # Utilities and helpers
├── webhook_monitor.py    # Webhook health monitoring
├── requirements.txt      # Python dependencies
├── Procfile             # Heroku configuration
├── .python-version      # Python version (3.11.6)
└── README.md           # This file
```

### Stateless State Management

**BotState Structure:**
```python
@dataclass
class BotState:
    promo_id: int = 0              # Current promo DB ID
    verified_at: int = 0           # Admin verification timestamp
    status_message_id: int = 0     # Status/welcome message ID
    promo_message_id: int = 0      # Current promo display message ID
    show_all_mode: bool = False    # Admin: show all vs active only
```

**Callback Data Encoding:**
```python
# Compressed format: action_p:promo_id_v:verified_at_m:promo_msg_id_s:status_msg_id_a:show_all
"next_p_5_v_1a2b3c4d_m_12_s_13_a_0"

# JSON fallback for complex state:
"state_{'a':'adminEdit','p':5,'v':1722176789,'s':123,'m':456,'all':1}"
```

**State Validation:**
- Timestamps prevent stale callback execution
- All user context embedded in button data  
- No server-side session storage
- Automatic fallback for invalid states

### Data Models

**Promo Message:**
```json
{
  "id": 1,
  "text": "Promotional content text",
  "image_file_id": "telegram_file_id_or_empty",
  "link": "https://example.com_or_empty", 
  "order": 10,
  "status": "active|draft|inactive",
  "created_by": "user_id",
  "created_at": "2024-01-01T00:00:00"
}
```

**Authorization:**
```json
{
  "admin_id": 1,
  "user_id": "123456789",
  "added_at": "2024-01-01"
}
```

**Note**: Currently stores Telegram user_id for admin verification.  
**TODO**: Hash user_ids or implement password-only authentication system.

## 🛠️ Management

### Bot Commands
| Command | Access | Description |
|---------|--------|-------------|
| `/start` | All | Start bot and show first promo |
| `/login [password]` | All | Admin authentication with onboarding password |

### Status Values
| Status | Description | User Visible | Admin Visible |
|--------|-------------|--------------|---------------|
| `active` | Published and live | ✅ Yes | ✅ Yes |
| `draft` | Work in progress | ❌ No | ✅ Yes |
| `inactive` | Hidden but preserved | ❌ No | ✅ Yes |

### Order System
- **Default increment**: +10 (10, 20, 30, 40...)
- **Easy insertion**: Add 15 between 10 and 20
- **Custom ordering**: Edit order field in Google Sheets
- **Display order**: Lower numbers appear first

### Admin Verification
- **Development**: 10 minutes (for testing)
- **Production**: 24 hours
- **Method**: User ID match in authorized_users sheet or `/login [password]`
- **Automatic refresh**: On each admin action
- **TODO**: Implement more secure authentication (hash user_ids or password-only system)

## 🔍 Troubleshooting

### Common Issues

**"Access Denied" / No Admin Buttons**
- Verify user_id in `authorized_users` sheet (column B)
- Try `/login [password]` with correct onboarding password
- Ensure Google Sheets has service account Editor access
- Try `/start` to refresh admin verification

**Images Not Displaying**
- Images must be uploaded through Telegram (not external URLs)
- Check if `image_file_id` is properly stored in sheets
- Verify image under Telegram limits (20MB per file)
- Set `DEFAULT_IMAGE_FILE_ID` env var for fallback image

**Bot Not Responding**
```bash
heroku logs --tail --app your-app-name    # Check for errors
heroku ps --app your-app-name             # Verify dyno running  
heroku restart --app your-app-name        # Restart if needed
```

**"Callback Expired" Messages**
- Normal for old buttons (stateless design)
- Users should use `/start` to refresh
- No data is lost - state rebuilds from scratch

**Webhook Issues (Production)**
- Built-in webhook monitoring runs every 10 minutes
- Check logs for "Webhook health check" messages
- Manual webhook reset: redeploy or restart dyno

### Development Setup
```bash
git clone your-repo
cd your-bot-folder

# Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Environment setup
cp .env.example .env
# Edit .env with your tokens and credentials

# Run locally (polling mode)
python app.py
```

### Debugging Commands
```bash
# Heroku production
heroku logs --tail --app your-app-name
heroku ps --app your-app-name
heroku config --app your-app-name
heroku restart --app your-app-name

# Local development
python app.py  # Shows detailed logs
```

## 🔐 Security & Compliance

### Stateless Compliance
- **Minimal Personal Data**: Only stores admin user_ids (TODO: implement hashing)
- **Russian Law Consideration**: Working toward full compliance
- **Session-Free Design**: No server-side user sessions
- **Auto-Expiring State**: Callback data expires naturally

### Access Control
- **Admin Authorization**: User ID matching in authorized_users sheet
- **Password Authentication**: `/login [password]` command with onboarding password
- **Service Account**: Limited Google Sheets access
- **Environment Variables**: Sensitive data in secure storage
- **Callback Validation**: State validation prevents tampering
- **TODO**: Implement more secure authentication system

### Best Practices
- Add admin user_ids directly to authorized_users sheet (column B)
- Use unique, strong bot tokens for dev/prod
- Set secure onboarding password in spreadsheet
- Limit service account to single spreadsheet
- Regular audit of authorized_users sheet
- Monitor logs for suspicious patterns

## 💰 Cost Analysis

### Heroku Hosting
- **Eco Dyno**: $5/month (sleeps after 30min)
- **Basic Dyno**: $7/month (always on, recommended)

### Google Services
- **Sheets API**: Free (100 requests/100 seconds - plenty)
- **Drive Storage**: Free (15GB limit)

### Telegram
- **Bot API**: Completely free
- **File Storage**: Free (20MB per file, 1.5GB total)

**Total: $5-7/month** (Heroku only)

## 🚀 Deployment Options

### Heroku (Current)
- Webhook-based operation
- Automatic webhook health monitoring
- Environment variable management
- Easy scaling and logs

### Alternative Platforms
- **Railway**: Similar to Heroku, competitive pricing
- **Render**: Free tier available, easy migration
- **DigitalOcean App Platform**: $5/month
- **Google Cloud Run**: Pay-per-use model

## 📈 Development & Extensions

### Architecture Benefits
- **Stateless = Scalable**: Handle unlimited concurrent users
- **Persistent UX**: Users never lose context
- **Zero Maintenance**: No session cleanup or user management
- **Fault Tolerant**: Graceful recovery from any error state

### Future Enhancements
- **Scheduling**: Auto-publish promos at specific times
- **Analytics**: Track promo views and click-through rates
- **Rich Media**: Video and document support
- **Bulk Operations**: CSV import/export for content
- **Multi-language**: Language selection and content

### Code Quality
- **Comprehensive Logging**: Detailed debug information
- **Error Recovery**: Graceful handling of all edge cases
- **Type Hints**: Full type annotation for maintainability
- **Modular Design**: Clear separation of concerns

## 🤝 Contributing

### Code Style
- Use double quotes for strings: `"text"`
- Stateless design principles throughout
- Comprehensive error handling
- Detailed logging for debugging

### Testing Stateless Design
```python
# Test state encoding/decoding
from state_manager import StateManager, BotState

state = BotState(promo_id=5, verified_at=1722176789, show_all_mode=True)
callback_data = StateManager.encode_state_for_callback("next", state)
action, decoded_state = StateManager.decode_callback_data(callback_data)

print(f"Original: {state}")
print(f"Callback: {callback_data}") 
print(f"Decoded: {action}, {decoded_state}")
```

## 📄 License

MIT License - Feel free to modify and distribute.

## 🆘 Support

### Getting Help
1. Check logs: `heroku logs --tail --app your-app-name`
2. Verify Google Sheets setup and service account permissions
3. Test bot tokens with Telegram API
4. Review state encoding/decoding in callback data

### Useful Resources
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Google Sheets API](https://developers.google.com/sheets/api)
- [Heroku Documentation](https://devcenter.heroku.com/)
- [python-telegram-bot Library](https://python-telegram-bot.readthedocs.io/)

---

**Ready to launch your stateless promotional content system? Deploy BC Loyalty Bot and start engaging users with persistent, manageable content that never loses context!** 🎉