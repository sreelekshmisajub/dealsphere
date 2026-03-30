# DealSphere Browser Extension

A powerful Chrome extension that brings DealSphere's price tracking and AI-powered shopping assistant to your browser while you shop.

## Features

### 🎯 Price Tracking
- **Automatic Detection**: Automatically detects products on supported e-commerce sites
- **Real-time Monitoring**: Tracks price changes in real-time
- **Price History**: View historical price trends with interactive charts
- **Cross-platform Comparison**: Compare prices across multiple stores

### 🚨 Smart Alerts
- **Custom Thresholds**: Set your target price and get notified when reached
- **Price Drop Predictions**: AI-powered predictions for future price drops
- **Multiple Channels**: Email, SMS, push notifications, and WhatsApp alerts
- **Bulk Management**: Create and manage multiple alerts efficiently

### 📊 Floating Widget
- **Instant Analysis**: Floating widget appears on product pages
- **Quick Actions**: Track products or set alerts with one click
- **Price Predictions**: See AI predictions for price drops
- **Minimizable**: Minimizes when not in use

### 📈 Statistics & Analytics
- **Savings Tracking**: Monitor your total savings from price drops
- **Performance Metrics**: View success rate and alert statistics
- **Data Export**: Export your tracking data for analysis

## Supported Sites

### Major E-commerce Platforms
- **Amazon** (amazon.com, amazon.in)
- **Flipkart** (flipkart.com)
- **Myntra** (myntra.com)
- **Ajio** (ajio.com)
- **Nykaa** (nykaa.com)
- **Tata Cliq** (tatacliq.com)
- **Croma** (croma.com)
- **Meesho** (meesho.com)

### Local Integration
- **200+ Local Stores** via DealSphere platform
- **Real-time inventory** from nearby merchants
- **Local price comparisons** with online deals

## Installation

### From Chrome Web Store
1. Visit Chrome Web Store
2. Search "DealSphere Price Tracker"
3. Click "Add to Chrome"
4. Grant necessary permissions

### Developer Installation
1. Clone this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked"
5. Select the extension folder

## Usage

### Automatic Product Detection
1. Visit any supported e-commerce site
2. Navigate to a product page
3. DealSphere widget automatically appears
4. Click "Track Price" or "Set Alert"

### Manual Tracking
1. Click the DealSphere icon in your browser toolbar
2. Go to "Tracked" tab
3. Paste product URL in "Quick Track"
4. Click "Track" button

### Managing Alerts
1. Open extension popup
2. Go to "Alerts" tab
3. View all active alerts
4. Edit target prices or delete alerts

### Viewing Statistics
1. Open extension popup
2. Go to "Stats" tab
3. View tracked products, savings, and performance
4. Export data for external analysis

## Configuration

### Notification Settings
- **Enable Notifications**: Turn on/off all notifications
- **Price Drop Threshold**: Set minimum percentage drop for alerts
- **Alert Frequency**: Choose instant, daily, or weekly summaries
- **Notification Channels**: Select preferred notification methods

### Advanced Settings
- **Auto-track Products**: Automatically track visited products
- **Currency Selection**: Choose display currency (INR, USD, EUR)
- **Data Management**: Clear tracking data or export for backup

## Technical Details

### Architecture
- **Manifest V3**: Uses latest Chrome extension standards
- **Background Service Worker**: Efficient background processing
- **Content Scripts**: Automatic product page integration
- **Storage API**: Local data persistence

### Security
- **Minimal Permissions**: Only requests necessary permissions
- **Privacy-focused**: No data shared with third parties
- **Secure Storage**: All data stored locally in browser
- **HTTPS Required**: Secure communication only

### Performance
- **Lightweight**: Minimal impact on browser performance
- **Efficient Monitoring**: Smart price checking algorithms
- **Background Processing**: Non-blocking operations
- **Memory Optimized**: Efficient data management

## API Integration

The extension integrates with DealSphere's backend APIs:

### Price Tracking API
```javascript
// Track a product
POST /api/v1/ai/track-product
{
  "url": "product_url",
  "target_price": 999.99,
  "user_id": "user_id"
}
```

### Price Prediction API
```javascript
// Get price predictions
POST /api/v1/ai/price-predict
{
  "product_id": "product_id",
  "days_ahead": 7
}
```

### Alert Management API
```javascript
// Create price alert
POST /api/v1/ai/create-alert
{
  "product_url": "product_url",
  "target_price": 999.99,
  "notification_settings": {...}
}
```

## Development

### File Structure
```
browser_extension/
├── manifest.json          # Extension manifest
├── background.js          # Background service worker
├── content.js             # Content script for product pages
├── popup.html             # Extension popup interface
├── popup.js               # Popup logic
├── icons/                 # Extension icons
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
└── README.md              # This file
```

### Building for Production
1. Minify JavaScript files
2. Optimize images
3. Update version numbers
4. Test on multiple sites
5. Submit to Chrome Web Store

### Debugging
1. Open Chrome Developer Tools
2. Go to Extensions tab
3. Find DealSphere extension
4. Click "background page" for background script
5. Check console for errors

## Privacy Policy

DealSphere extension:
- **Does not collect** personal information
- **Does not track** browsing history
- **Stores data locally** in your browser
- **Uses minimal permissions** for core functionality
- **Never shares** data with third parties

## Support

### Common Issues
1. **Widget not appearing**: Check if site is supported
2. **Price not updating**: Verify internet connection
3. **Alerts not working**: Check notification settings
4. **Extension not loading**: Restart browser

### Getting Help
- Email: support@dealsphere.com
- Documentation: docs.dealsphere.com
- Community: community.dealsphere.com
- Bug Reports: github.com/dealsphere/issues

## Updates

### Version History
- **v1.0.0**: Initial release with basic tracking
- **v1.1.0**: Added AI price predictions
- **v1.2.0**: Enhanced UI and notifications
- **v1.3.0**: Local store integration
- **v1.4.0**: Advanced analytics and export

### Upcoming Features
- **Mobile App Extension**: Cross-device synchronization
- **Advanced AI**: Machine learning for better predictions
- **Social Features**: Share deals with friends
- **Merchant Tools**: Direct merchant integration

## License

This extension is part of the DealSphere ecosystem and is licensed under the DealSphere Terms of Service.

---

**DealSphere Extension** - Your intelligent shopping companion for smarter online shopping! 🛍️✨
