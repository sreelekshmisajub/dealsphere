// Popup script for DealSphere Extension
class DealSpherePopup {
    constructor() {
        this.currentTab = 'tracked';
        this.settings = {};
        this.trackedProducts = [];
        this.alerts = [];
        
        this.initialize();
    }
    
    async initialize() {
        await this.loadData();
        this.setupEventListeners();
        this.renderCurrentTab();
    }
    
    async loadData() {
        return new Promise((resolve) => {
            chrome.storage.local.get(['settings', 'trackedProducts', 'alerts'], (result) => {
                this.settings = result.settings || {
                    notifications: true,
                    autoTrack: true,
                    priceDropThreshold: 5,
                    currency: 'INR'
                };
                
                this.trackedProducts = result.trackedProducts || [];
                this.alerts = result.alerts || [];
                
                this.updateSettingsUI();
                resolve();
            });
        });
    }
    
    setupEventListeners() {
        // Listen for storage changes
        chrome.storage.onChanged.addListener((changes, namespace) => {
            if (namespace === 'local') {
                this.loadData().then(() => {
                    this.renderCurrentTab();
                });
            }
        });
    }
    
    updateSettingsUI() {
        // Update toggle switches
        document.getElementById('notifications-toggle').classList.toggle('active', this.settings.notifications);
        document.getElementById('auto-track-toggle').classList.toggle('active', this.settings.autoTrack);
        
        // Update selects
        document.getElementById('threshold-select').value = this.settings.priceDropThreshold;
        document.getElementById('currency-select').value = this.settings.currency;
    }
    
    renderCurrentTab() {
        switch (this.currentTab) {
            case 'tracked':
                this.renderTrackedProducts();
                break;
            case 'alerts':
                this.renderAlerts();
                break;
            case 'stats':
                this.renderStats();
                break;
            case 'settings':
                // Settings already rendered in HTML
                break;
        }
    }
    
    renderTrackedProducts() {
        const container = document.getElementById('tracked-products');
        
        if (this.trackedProducts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <img src="icons/icon48.png" alt="No products">
                    <p>No products tracked yet</p>
                    <p style="font-size: 12px; color: #999;">Visit a product page to start tracking</p>
                </div>
            `;
            return;
        }
        
        const productsHTML = this.trackedProducts.map(product => {
            const priceChange = this.calculatePriceChange(product);
            const changeClass = priceChange > 0 ? 'price-up' : 'price-down';
            const changeSymbol = priceChange > 0 ? '↑' : '↓';
            
            return `
                <div class="tracked-product">
                    <div class="product-name">${product.name}</div>
                    <div class="product-price">${this.formatCurrency(product.price)}</div>
                    <div class="product-meta">
                        <span>${product.site}</span>
                        <span class="price-change ${changeClass}">
                            ${changeSymbol} ${Math.abs(priceChange)}%
                        </span>
                    </div>
                    <div style="margin-top: 8px;">
                        <button class="btn btn-secondary btn-sm" onclick="dealsphere.viewProduct('${product.url}')">View</button>
                        <button class="btn btn-primary btn-sm" onclick="dealsphere.untrackProduct('${product.id}')">Untrack</button>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = productsHTML;
    }
    
    renderAlerts() {
        const container = document.getElementById('price-alerts');
        
        if (this.alerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <img src="icons/icon48.png" alt="No alerts">
                    <p>No price alerts set</p>
                    <p style="font-size: 12px; color: #999;">Set alerts to get notified of price drops</p>
                </div>
            `;
            return;
        }
        
        const alertsHTML = this.alerts.map(alert => {
            const currentPrice = this.getCurrentPrice(alert.url);
            const targetPrice = alert.targetPrice;
            const status = currentPrice <= targetPrice ? 'Target Reached! 🎉' : 'Waiting for drop';
            const statusClass = currentPrice <= targetPrice ? 'text-success' : 'text-warning';
            
            return `
                <div class="tracked-product">
                    <div class="product-name">${alert.name}</div>
                    <div class="product-price">Target: ${this.formatCurrency(targetPrice)}</div>
                    <div class="product-meta">
                        <span>Current: ${this.formatCurrency(currentPrice)}</span>
                        <span class="${statusClass}">${status}</span>
                    </div>
                    <div style="margin-top: 8px;">
                        <button class="btn btn-primary btn-sm" onclick="dealsphere.editAlert('${alert.id}')">Edit</button>
                        <button class="btn btn-secondary btn-sm" onclick="dealsphere.deleteAlert('${alert.id}')">Delete</button>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = alertsHTML;
    }
    
    renderStats() {
        // Update statistics
        document.getElementById('total-tracked').textContent = this.trackedProducts.length;
        document.getElementById('total-alerts').textContent = this.alerts.length;
        
        // Calculate total savings
        const totalSavings = this.calculateTotalSavings();
        document.getElementById('total-savings').textContent = this.formatCurrency(totalSavings);
        
        // Count price drops
        const priceDrops = this.trackedProducts.filter(p => this.calculatePriceChange(p) < 0).length;
        document.getElementById('price-drops').textContent = priceDrops;
    }
    
    calculatePriceChange(product) {
        if (!product.priceHistory || product.priceHistory.length < 2) {
            return 0;
        }
        
        const latest = product.priceHistory[product.priceHistory.length - 1].price;
        const previous = product.priceHistory[product.priceHistory.length - 2].price;
        
        return ((latest - previous) / previous) * 100;
    }
    
    calculateTotalSavings() {
        return this.trackedProducts.reduce((total, product) => {
            const change = this.calculatePriceChange(product);
            return change < 0 ? total + Math.abs(change * product.price / 100) : total;
        }, 0);
    }
    
    getCurrentPrice(url) {
        const product = this.trackedProducts.find(p => p.url === url);
        return product ? product.price : 0;
    }
    
    formatCurrency(amount) {
        const symbols = {
            'INR': '₹',
            'USD': '$',
            'EUR': '€'
        };
        
        const symbol = symbols[this.settings.currency] || '₹';
        return `${symbol}${amount.toFixed(2)}`;
    }
    
    async quickTrack() {
        const input = document.getElementById('quick-track-url');
        const url = input.value.trim();
        
        if (!url) {
            alert('Please enter a product URL');
            return;
        }
        
        // Extract product info from URL (simplified)
        const productData = {
            url: url,
            name: 'Product from URL',
            price: Math.random() * 10000 + 1000,
            site: this.extractSiteName(url),
            id: Date.now().toString(),
            trackedAt: Date.now()
        };
        
        // Add to tracked products
        this.trackedProducts.push(productData);
        
        // Save to storage
        chrome.storage.local.set({ trackedProducts: this.trackedProducts }, () => {
            input.value = '';
            this.renderTrackedProducts();
            
            // Show success message
            this.showNotification('Product tracking started!', 'success');
        });
    }
    
    extractSiteName(url) {
        const domain = new URL(url).hostname;
        if (domain.includes('amazon')) return 'Amazon';
        if (domain.includes('flipkart')) return 'Flipkart';
        if (domain.includes('myntra')) return 'Myntra';
        return 'Store';
    }
    
    untrackProduct(productId) {
        this.trackedProducts = this.trackedProducts.filter(p => p.id !== productId);
        chrome.storage.local.set({ trackedProducts: this.trackedProducts }, () => {
            this.renderTrackedProducts();
            this.showNotification('Product untracked', 'info');
        });
    }
    
    editAlert(alertId) {
        const alert = this.alerts.find(a => a.id === alertId);
        if (!alert) return;
        
        const newTargetPrice = prompt('Set new target price:', alert.targetPrice);
        if (newTargetPrice && !isNaN(newTargetPrice)) {
            alert.targetPrice = parseFloat(newTargetPrice);
            chrome.storage.local.set({ alerts: this.alerts }, () => {
                this.renderAlerts();
                this.showNotification('Alert updated', 'success');
            });
        }
    }
    
    deleteAlert(alertId) {
        if (confirm('Are you sure you want to delete this alert?')) {
            this.alerts = this.alerts.filter(a => a.id !== alertId);
            chrome.storage.local.set({ alerts: this.alerts }, () => {
                this.renderAlerts();
                this.showNotification('Alert deleted', 'info');
            });
        }
    }
    
    viewProduct(url) {
        chrome.tabs.create({ url: url });
    }
    
    toggleSetting(setting) {
        this.settings[setting] = !this.settings[setting];
        chrome.storage.local.set({ settings: this.settings }, () => {
            this.updateSettingsUI();
        });
    }
    
    updateThreshold() {
        const threshold = parseInt(document.getElementById('threshold-select').value);
        this.settings.priceDropThreshold = threshold;
        chrome.storage.local.set({ settings: this.settings });
    }
    
    updateCurrency() {
        const currency = document.getElementById('currency-select').value;
        this.settings.currency = currency;
        chrome.storage.local.set({ settings: this.settings });
        this.renderCurrentTab(); // Re-render to update currency formatting
    }
    
    clearData() {
        if (confirm('Are you sure you want to clear all tracked data? This cannot be undone.')) {
            chrome.storage.local.set({
                trackedProducts: [],
                alerts: []
            }, () => {
                this.trackedProducts = [];
                this.alerts = [];
                this.renderCurrentTab();
                this.showNotification('All data cleared', 'info');
            });
        }
    }
    
    exportData() {
        const data = {
            trackedProducts: this.trackedProducts,
            alerts: this.alerts,
            settings: this.settings,
            exportDate: new Date().toISOString()
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `dealsphere-data-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: ${type === 'success' ? '#28A745' : type === 'error' ? '#DC3545' : '#17A2B8'};
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            z-index: 1000;
            font-size: 14px;
            font-weight: 500;
        `;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}

// Tab switching function
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Update current tab and render
    dealsphere.currentTab = tabName;
    dealsphere.renderCurrentTab();
}

// Initialize popup
const dealsphere = new DealSpherePopup();
