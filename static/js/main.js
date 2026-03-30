/* DealSphere Main JS - Interactions & Micro-animations */

document.addEventListener('DOMContentLoaded', () => {
    // Navbar Scroll Effect
    const navbar = document.querySelector('.navbar-premium');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }

    // Initialize Tooltips & Popovers (Bootstrap)
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize intersection observer for various scroll effects
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                // Keep observing if we want it to hide/show, but unobserve for better performance
                // observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    animatedElements.forEach((el) => observer.observe(el));
});

// Barcode & Image Search Modal Logic - Full AI Integration
async function openBarcodeScanner(barcodeInput = '') {
    const barcode = barcodeInput || prompt('Enter or Scan Barcode:');
    if (!barcode) return;
    
    // AI fetch for barcode scanning
    try {
        const response = await fetch('/api/v1/ai/barcode-search/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ barcode: barcode })
        });
        
        const data = await response.json();
        if (data.found) {
            alert(`Found: ${data.product.name} at ₹${data.product.price}`);
            // In a real implementation, we would redirect to product detail
            // window.location.href = `/product/${data.product.product_id}/`;
        } else {
            alert('Barcode not found in our AI database.');
        }
    } catch (error) {
        console.error('AI Error (Barcode):', error);
        alert('Barcode search failed. Please try again.');
    }
}

async function openImageSearch() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        // Show premium loading state
        alert('AI identifying product from image: ' + file.name + '...');
        
        // Form Data for multipart upload
        const formData = new FormData();
        formData.append('image', file);
        
        try {
            const response = await fetch('/api/v1/ai/identify-product/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            
            const data = await response.json();
            if (data.predicted_category) {
                alert(`AI Prediction: ${data.predicted_category} (${Math.round(data.confidence * 100)}% accuracy)`);
                // Use data.matching_products to show results
            }
        } catch (error) {
            console.error('AI Error (Image):', error);
            alert('Product identification failed.');
        }
    };
    input.click();
}

// Basket Optimization Call
async function optimizeBasketAI() {
    try {
        const response = await fetch('/api/v1/ai/basket-optimize/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        
        const data = await response.json();
        if (data.optimized_basket) {
            alert(`AI Suggestion: Split your order into ${data.optimized_basket.split_count} stores to save ₹${data.optimized_basket.savings}`);
        }
    } catch (error) {
        console.error('AI Error (Basket):', error);
    }
}

// CSRF Token Helper
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Quick Add to Cart with Premium Feedback
function addToCartPremium(productId) {
    // Show a premium toast notification
    const toast = document.createElement('div');
    toast.className = 'alert glass position-fixed bottom-0 end-0 m-4 shadow-xl z-3 animate-fade-in-up';
    toast.style.minWidth = '300px';
    toast.style.transition = 'all 0.5s ease-in-out';
    toast.innerHTML = `
        <div class="d-flex align-items-center gap-3">
            <div class="bg-success text-white rounded-circle p-2 d-flex align-items-center justify-content-center" style="width: 32px; height: 32px;">
                <i class="fas fa-check smaller text-white"></i>
            </div>
            <div>
                <h6 class="fw-bold mb-0 smaller text-black">Success!</h6>
                <p class="mb-0 smallest text-secondary" style="font-size: 0.75rem;">Added to your comparison cart.</p>
            </div>
        </div>
    `;
    document.body.appendChild(toast);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 500);
    }, 3000);
}
