// Background script for DealSphere Extension
class DealSphereBackground {
    constructor() {
        this.initializeExtension();
        this.setupEventListeners();
    }
    
    initializeExtension() {
        console.log('DealSphere Extension initialized');
        
        // Initialize storage with default values
        chrome.storage.local.get(['settings', 'trackedProducts', 'alerts'], (result) => {
            if (!result.settings) {
                chrome.storage.local.set({
                    settings: {
                        notifications: true,
                        autoTrack: true,
                        priceDropThreshold: 5,
                        currency: 'INR'
                    }
                });
            }
            
            if (!result.trackedProducts) {
                chrome.storage.local.set({ trackedProducts: [] });
            }
            
            if (!result.alerts) {
                chrome.storage.local.set({ alerts: [] });
            }
        });
    }
    
    setupEventListeners() {
        // Listen for tab updates to detect product pages
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            if (changeInfo.status === 'complete' && tab.url) {
                this.detectProductPage(tabId, tab.url);
            }
        });
        
        // Listen for extension icon click
        chrome.action.onClicked.addListener((tab) => {
            this.openPopup(tab);
        });
        
        // Listen for messages from content script
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            this.handleMessage(request, sender, sendResponse);
        });
        
        // Set up periodic price checking
        this.startPriceMonitoring();
    }
    
    detectProductPage(tabId, url) {
        const supportedSites = [
            'amazon.com', 'amazon.in',
            'flipkart.com',
            'myntra.com', 'ajio.com',
            'nykaa.com', 'tatacliq.com',
            'croma.com', 'meesho.com'
        ];
        
        const isProductPage = supportedSites.some(site => url.includes(site)) && 
                            (url.includes('/dp/') || url.includes('/product/') || url.includes('/p/'));
        
        if (isProductPage) {
            this.showPriceTracker(tabId, url);
        }
    }
    
    showPriceTracker(tabId, url) {
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ['content.js']
        });
    }
    
    openPopup(tab) {
        chrome.action.openPopup();
    }
    
    handleMessage(request, sender, sendResponse) {
        switch (request.action) {
            case 'trackProduct':
                this.trackProduct(request.data, sendResponse);
                break;
            case 'getProductInfo':
                this.getProductInfo(request.productId, sendResponse);
                break;
            case 'createAlert':
                this.createPriceAlert(request.data, sendResponse);
                break;
            case 'updateSettings':
                this.updateSettings(request.data, sendResponse);
                break;
            default:
                sendResponse({ error: 'Unknown action' });
        }
        return true; // Keep message channel open for async response
    }
    
    async trackProduct(productData, sendResponse) {
        try {
            // Store product in local storage
            chrome.storage.local.get(['trackedProducts'], (result) => {
                const products = result.trackedProducts || [];
                
                // Check if product already exists
                const existingIndex = products.findIndex(p => p.url === productData.url);
                if (existingIndex >= 0) {
                    products[existingIndex] = { ...products[existingIndex], ...productData, lastUpdated: Date.now() };
                } else {
                    products.push({ ...productData, id: Date.now().toString(), trackedAt: Date.now() });
                }
                
                chrome.storage.local.set({ trackedProducts: products }, () => {
                    sendResponse({ success: true, productId: productData.id });
                });
            });
            
            // Start price monitoring for this product
            this.monitorProductPrice(productData);
            
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
    }
    
    async monitorProductPrice(productData) {
        // Simulate price monitoring
        setInterval(async () => {
            const currentPrice = await this.fetchCurrentPrice(productData.url);
            const previousPrice = productData.price;
            
            if (currentPrice < previousPrice) {
                const dropPercentage = ((previousPrice - currentPrice) / previousPrice) * 100;
                
                chrome.storage.local.get(['settings'], (result) => {
                    const settings = result.settings || {};
                    
                    if (dropPercentage >= settings.priceDropThreshold) {
                        this.sendPriceDropNotification(productData, currentPrice, dropPercentage);
                    }
                });
                
                // Update stored price
                chrome.storage.local.get(['trackedProducts'], (result) => {
                    const products = result.trackedProducts || [];
                    const productIndex = products.findIndex(p => p.url === productData.url);
                    
                    if (productIndex >= 0) {
                        products[productIndex].price = currentPrice;
                        products[productIndex].priceHistory = products[productIndex].priceHistory || [];
                        products[productIndex].priceHistory.push({
                            price: currentPrice,
                            date: Date.now()
                        });
                        
                        chrome.storage.local.set({ trackedProducts: products });
                    }
                });
            }
        }, 60000); // Check every minute
    }
    
    async fetchCurrentPrice(url) {
        // In a real implementation, this would use a backend API to fetch current price
        // For demo purposes, return a simulated price
        return Math.random() * 10000 + 1000;
    }
    
    sendPriceDropNotification(productData, newPrice, dropPercentage) {
        chrome.storage.local.get(['settings'], (result) => {
            const settings = result.settings || {};
            
            if (settings.notifications) {
                chrome.notifications.create({
                    type: 'basic',
                    iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                    title: 'Price Drop Alert! 🎉',
                    message: `${productData.name} dropped by ${dropPercentage.toFixed(1)}%\nNew price: ₹${newPrice.toFixed(2)}`
                });
            }
        });
    }
    
    createPriceAlert(alertData, sendResponse) {
        chrome.storage.local.get(['alerts'], (result) => {
            const alerts = result.alerts || [];
            alerts.push({
                ...alertData,
                id: Date.now().toString(),
                createdAt: Date.now()
            });
            
            chrome.storage.local.set({ alerts: alerts }, () => {
                sendResponse({ success: true, alertId: alertData.id });
            });
        });
    }
    
    updateSettings(newSettings, sendResponse) {
        chrome.storage.local.get(['settings'], (result) => {
            const settings = { ...result.settings, ...newSettings };
            chrome.storage.local.set({ settings: settings }, () => {
                sendResponse({ success: true, settings: settings });
            });
        });
    }
    
    startPriceMonitoring() {
        // Check all tracked products every 30 minutes
        setInterval(() => {
            chrome.storage.local.get(['trackedProducts'], (result) => {
                const products = result.trackedProducts || [];
                products.forEach(product => {
                    this.monitorProductPrice(product);
                });
            });
        }, 30 * 60 * 1000); // 30 minutes
    }
}

// Initialize the background script
new DealSphereBackground();
