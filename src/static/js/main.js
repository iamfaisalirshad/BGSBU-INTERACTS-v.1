// Toast notification system
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const icons = {
        success: 'check-circle-fill',
        danger: 'exclamation-triangle-fill',
        warning: 'exclamation-circle-fill',
        info: 'info-circle-fill'
    };

    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show shadow-lg d-flex align-items-center`;
    toast.style.cssText = 'min-width:300px;animation:fadeInUp .3s ease';
    toast.innerHTML = `
        <i class="bi bi-${icons[type] || 'info-circle-fill'} me-2"></i>
        <div>${message}</div>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Loading spinner management
function showLoadingSpinner(text = 'Loading...') {
    let spinner = document.getElementById('global-spinner');
    if (!spinner) {
        spinner = document.createElement('div');
        spinner.id = 'global-spinner';
        spinner.className = 'spinner-overlay';
        spinner.innerHTML = `
            <div class="spinner-content">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2 text-white">${text}</p>
            </div>
        `;
        document.body.appendChild(spinner);
    } else {
        spinner.style.display = 'flex';
        spinner.querySelector('p').textContent = text;
    }
}

function hideLoadingSpinner() {
    const spinner = document.getElementById('global-spinner');
    if (spinner) {
        spinner.style.display = 'none';
    }
}

// Form validation helper
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;

    let isValid = true;
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Submit form with loading state
function submitFormWithLoading(form, endpoint, method = 'POST') {
    return new Promise((resolve, reject) => {
        const formData = new FormData(form);
        showLoadingSpinner('Processing...');

        fetch(endpoint, {
            method: method,
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            hideLoadingSpinner();
            if (data.success) {
                showToast(data.message || 'Success!', 'success');
                resolve(data);
            } else {
                showToast(data.message || 'An error occurred', 'danger');
                reject(data);
            }
        })
        .catch(error => {
            hideLoadingSpinner();
            showToast('Network error. Please try again.', 'danger');
            reject(error);
        });
    });
}

// Initialize flash messages with auto-dismiss
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss flash messages
    document.querySelectorAll('.flash-messages .alert').forEach(alert => {
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Add loading states to all forms
    document.querySelectorAll('form[data-loading-text]').forEach(form => {
        form.addEventListener('submit', function(e) {
            const btn = form.querySelector('button[type="submit"]');
            if (btn) {
                const originalText = btn.innerHTML;
                const loadingText = form.getAttribute('data-loading-text') || 'Processing...';
                btn.disabled = true;
                btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${loadingText}`;
                
                // Restore button after request completes
                setTimeout(() => {
                    if (btn.disabled) {
                        btn.disabled = false;
                        btn.innerHTML = originalText;
                    }
                }, 30000); // 30 second timeout
            }
        });
    });
});

// Debounce utility for search/filter operations
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Enhanced error handling for API calls
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API Error:', error);
        showToast(error.message || 'An error occurred. Please try again.', 'danger');
        throw error;
    }
}

// Smooth scroll to element
function smoothScroll(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Confirm action before proceeding
function confirmAction(message = 'Are you sure?') {
    return new Promise((resolve) => {
        if (confirm(message)) {
            resolve(true);
        } else {
            resolve(false);
        }
    });
}
