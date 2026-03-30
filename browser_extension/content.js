// Content script for DealSphere Extension
class DealSphereContent {
    constructor() {
        this.siteConfig = this.getSiteConfig();
        this.productData = null;
        this.initialize();
    }
    
    getSiteConfig() {
        const configs = {
            'amazon': {
                name: 'Amazon',
                selectors: {
                    title: '#productTitle, .product-title',
                    price: '.a-price .a-offscreen, .a-price-whole',
                    image: '#landingImage, .imgTagWrapper img',
                    rating: '.a-icon-alt, .reviewStars',
                    description: '#feature-bullets ul, #productDescription'
                },
                priceParser: (priceText) => {
                    const match = priceText.match(/[\d,]+\.?\d*/);
                    return match ? parseFloat(match[0].replace(',', '')) : null;
                }
            },
            'flipkart': {
                name: 'Flipkart',
                selectors: {
                    title: '.B_NuCI, .product-title',
                    price: '._30jeq3, ._16Jk6d',
                    image: '._396cs4 img',
                    rating: '._2LmwQv, .eMSTdx',
                    description: '_1mXcCf, .product-description'
                },
                priceParser: (priceText) => {
                    const match = priceText.match(/[\d,]+\.?\d*/);
                    return match ? parseFloat(match[0].replace(',', '')) : null;
                }
            },
            'myntra': {
                name: 'Myntra',
                selectors: {
                    title: '.pdp-title, .product-title',
                    price: '.pdp-price, .price-display',
                    image: '.image-grid-image img',
                    rating: '.index-overallRating, .rating-count',
                    description: '.pdp-description, .product-description'
                },
                priceParser: (priceText) => {
                    const match = priceText.match(/[\d,]+\.?\d*/);
                    return match ? parseFloat(match[0].replace(',', '')) : null;
                }
            }
        };
        
        const hostname = window.location.hostname.toLowerCase();
        for (const [key, config] of Object.entries(configs)) {
            if (hostname.includes(key)) {
                return config;
            }
        }
        
        return null;
    }
    
    initialize() {
        if (!this.siteConfig) {
            console.log('DealSphere: Site not supported');
            return;
        }
        
        console.log(`DealSphere: Initialized for ${this.siteConfig.name}`);
        
        // Wait for page to load completely
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.extractProductData());
        } else {
            this.extractProductData();
        }
        
        // Create floating widget
        this.createFloatingWidget();
    }
    
    extractProductData() {
        const data = {
            url: window.location.href,
            site: this.siteConfig.name,
            timestamp: Date.now()
        };
        
        // Extract product title
        const titleElement = document.querySelector(this.siteConfig.selectors.title);
        if (titleElement) {
            data.name = titleElement.textContent.trim();
        }
        
        // Extract price
        const priceElement = document.querySelector(this.siteConfig.selectors.price);
        if (priceElement) {
            const priceText = priceElement.textContent.trim();
            data.price = this.siteConfig.priceParser(priceText);
            data.priceText = priceText;
        }
        
        // Extract image
        const imageElement = document.querySelector(this.siteConfig.selectors.image);
        if (imageElement) {
            data.image = imageElement.src || imageElement.getAttribute('data-src');
        }
        
        // Extract rating
        const ratingElement = document.querySelector(this.siteConfig.selectors.rating);
        if (ratingElement) {
            const ratingText = ratingElement.textContent.trim();
            const ratingMatch = ratingText.match(/[\d.]+/);
            data.rating = ratingMatch ? parseFloat(ratingMatch[0]) : null;
        }
        
        // Extract description
        const descriptionElement = document.querySelector(this.siteConfig.selectors.description);
        if (descriptionElement) {
            data.description = descriptionElement.textContent.trim().substring(0, 500);
        }
        
        this.productData = data;
        console.log('DealSphere: Product data extracted', data);
        
        // Update widget with product data
        this.updateWidget();
        
        // Send data to background script
        chrome.runtime.sendMessage({
            action: 'productDetected',
            data: data
        });
    }
    
    createFloatingWidget() {
        // Create floating widget container
        const widget = document.createElement('div');
        widget.id = 'dealsphere-widget';
        widget.innerHTML = `
            <div class="dealsphere-widget-container">
                <div class="dealsphere-widget-header">
                    <img src="${chrome.runtime.getURL('icons/icon32.png')}" alt="DealSphere">
                    <span>DealSphere</span>
                    <button class="dealsphere-close">&times;</button>
                </div>
                <div class="dealsphere-widget-content">
                    <div class="dealsphere-loading">
                        <div class="dealsphere-spinner"></div>
                        <p>Analyzing product...</p>
                    </div>
                </div>
            </div>
        `;
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #dealsphere-widget {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .dealsphere-widget-container {
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                width: 320px;
                max-height: 500px;
                overflow: hidden;
                border: 1px solid #e0e0e0;
            }
            
            .dealsphere-widget-header {
                background: linear-gradient(135deg, #FF6B35 0%, #F7931E 100%);
                color: white;
                padding: 12px 16px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-weight: 600;
            }
            
            .dealsphere-widget-header img {
                width: 20px;
                height: 20px;
                margin-right: 8px;
            }
            
            .dealsphere-close {
                background: none;
                border: none;
                color: white;
                font-size: 20px;
                cursor: pointer;
                padding: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: background 0.2s;
            }
            
            .dealsphere-close:hover {
                background: rgba(255,255,255,0.2);
            }
            
            .dealsphere-widget-content {
                padding: 16px;
                max-height: 400px;
                overflow-y: auto;
            }
            
            .dealsphere-loading {
                text-align: center;
                padding: 20px;
                color: #666;
            }
            
            .dealsphere-spinner {
                border: 3px solid #f3f3f3;
                border-top: 3px solid #FF6B35;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: dealsphere-spin 1s linear infinite;
                margin: 0 auto 10px;
            }
            
            @keyframes dealsphere-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .dealsphere-product-info {
                margin-bottom: 16px;
            }
            
            .dealsphere-product-title {
                font-weight: 600;
                font-size: 14px;
                margin-bottom: 8px;
                line-height: 1.4;
                color: #333;
            }
            
            .dealsphere-product-price {
                font-size: 18px;
                font-weight: 700;
                color: #FF6B35;
                margin-bottom: 8px;
            }
            
            .dealsphere-product-rating {
                display: flex;
                align-items: center;
                gap: 4px;
                margin-bottom: 12px;
                font-size: 14px;
                color: #666;
            }
            
            .dealsphere-actions {
                display: flex;
                gap: 8px;
                margin-top: 16px;
            }
            
            .dealsphere-btn {
                flex: 1;
                padding: 8px 12px;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .dealsphere-btn-primary {
                background: #FF6B35;
                color: white;
            }
            
            .dealsphere-btn-primary:hover {
                background: #F7931E;
            }
            
            .dealsphere-btn-secondary {
                background: #f0f0f0;
                color: #333;
            }
            
            .dealsphere-btn-secondary:hover {
                background: #e0e0e0;
            }
            
            .dealsphere-price-prediction {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 12px;
                margin-top: 12px;
            }
            
            .dealsphere-prediction-title {
                font-weight: 600;
                font-size: 12px;
                margin-bottom: 8px;
                color: #333;
            }
            
            .dealsphere-prediction-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 4px;
                font-size: 11px;
            }
            
            .dealsphere-prediction-chance {
                background: #28A745;
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
            }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(widget);
        
        // Add close handler
        widget.querySelector('.dealsphere-close').addEventListener('click', () => {
            widget.style.display = 'none';
        });
        
        // Minimize after 10 seconds if no interaction
        setTimeout(() => {
            if (widget.style.display !== 'none') {
                widget.querySelector('.dealsphere-widget-content').style.display = 'none';
                widget.querySelector('.dealsphere-widget-header').style.cursor = 'pointer';
                widget.querySelector('.dealsphere-widget-header').addEventListener('click', () => {
                    widget.querySelector('.dealsphere-widget-content').style.display = 'block';
                });
            }
        }, 10000);
    }
    
    updateWidget() {
        if (!this.productData) return;
        
        const content = document.querySelector('.dealsphere-widget-content');
        
        const widgetHTML = `
            <div class="dealsphere-product-info">
                <div class="dealsphere-product-title">${this.productData.name || 'Product'}</div>
                ${this.productData.price ? `<div class="dealsphere-product-price">₹${this.productData.price.toFixed(2)}</div>` : ''}
                ${this.productData.rating ? `
                    <div class="dealsphere-product-rating">
                        <span>⭐ ${this.productData.rating}</span>
                    </div>
                ` : ''}
            </div>
            
            <div class="dealsphere-price-prediction">
                <div class="dealsphere-prediction-title">🔮 Price Drop Prediction</div>
                <div class="dealsphere-prediction-item">
                    <span>Next 2-3 days</span>
                    <span class="dealsphere-prediction-chance">75%</span>
                </div>
                <div class="dealsphere-prediction-item">
                    <span>Next week</span>
                    <span class="dealsphere-prediction-chance">60%</span>
                </div>
                <div class="dealsphere-prediction-item">
                    <span>Next month</span>
                    <span class="dealsphere-prediction-chance">40%</span>
                </div>
            </div>
            
            <div class="dealsphere-actions">
                <button class="dealsphere-btn dealsphere-btn-primary" onclick="dealsphere.trackProduct()">
                    <i class="fas fa-chart-line"></i> Track Price
                </button>
                <button class="dealsphere-btn dealsphere-btn-secondary" onclick="dealsphere.setAlert()">
                    <i class="fas fa-bell"></i> Set Alert
                </button>
            </div>
        `;
        
        content.innerHTML = widgetHTML;
    }
    
    trackProduct() {
        if (!this.productData) return;
        
        chrome.runtime.sendMessage({
            action: 'trackProduct',
            data: this.productData
        }, (response) => {
            if (response.success) {
                this.showNotification('Product tracking started!', 'success');
            } else {
                this.showNotification('Failed to track product', 'error');
            }
        });
    }
    
    setAlert() {
        if (!this.productData) return;
        
        const targetPrice = prompt('Set your target price (₹):', '');
        if (targetPrice && !isNaN(targetPrice)) {
            chrome.runtime.sendMessage({
                action: 'createAlert',
                data: {
                    ...this.productData,
                    targetPrice: parseFloat(targetPrice)
                }
            }, (response) => {
                if (response.success) {
                    this.showNotification('Price alert created!', 'success');
                } else {
                    this.showNotification('Failed to create alert', 'error');
                }
            });
        }
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: ${type === 'success' ? '#28A745' : '#DC3545'};
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 10001;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        `;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}

// Initialize the content script
const dealsphere = new DealSphereContent();
