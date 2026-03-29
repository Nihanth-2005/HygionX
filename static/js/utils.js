// Utility functions for HygionX frontend

// Form validation utilities
const FormValidator = {
    validateEmail: (email) => {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },

    validatePassword: (password) => {
        return password.length >= 8;
    },

    validateAge: (age) => {
        const ageNum = parseInt(age);
        return ageNum >= 1 && ageNum <= 120;
    },

    showError: (fieldId, message) => {
        const field = document.getElementById(fieldId);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'text-red-600 text-sm mt-1';
        errorDiv.textContent = message;
        
        // Remove existing error
        const existingError = field.parentNode.querySelector('.text-red-600');
        if (existingError) {
            existingError.remove();
        }
        
        field.parentNode.appendChild(errorDiv);
        field.classList.add('border-red-500');
    },

    clearError: (fieldId) => {
        const field = document.getElementById(fieldId);
        const existingError = field.parentNode.querySelector('.text-red-600');
        if (existingError) {
            existingError.remove();
        }
        field.classList.remove('border-red-500');
    }
};

// Loading states
const LoadingManager = {
    show: (button, originalText) => {
        button.disabled = true;
        button.dataset.originalText = originalText;
        button.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Loading...';
    },

    hide: (button) => {
        button.disabled = false;
        button.innerHTML = button.dataset.originalText || 'Submit';
    }
};

// Toast notifications
const Toast = {
    show: (message, type = 'info') => {
        const toast = document.createElement('div');
        const bgColor = type === 'success' ? 'bg-green-500' : 
                       type === 'error' ? 'bg-red-500' : 
                       type === 'warning' ? 'bg-yellow-500' : 'bg-blue-500';
        
        toast.className = `fixed top-4 right-4 ${bgColor} text-white px-6 py-3 rounded-lg shadow-lg z-50 flex items-center space-x-2`;
        toast.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
            <span>${message}</span>
        `;
        
        document.body.appendChild(toast);
        
        // Auto remove after 3 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
};

// Modal management
const Modal = {
    show: (modalId) => {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            modal.classList.add('flex');
            document.body.style.overflow = 'hidden';
        }
    },

    hide: (modalId) => {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.body.style.overflow = 'auto';
        }
    },

    create: (title, content, actions = []) => {
        const modalId = 'modal_' + Date.now();
        const modal = document.createElement('div');
        modal.id = modalId;
        modal.className = 'hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        const actionButtons = actions.map(action => 
            `<button onclick="${action.onclick}" class="px-4 py-2 rounded-lg ${action.class || 'bg-blue-600 text-white'}">${action.text}</button>`
        ).join('');
        
        modal.innerHTML = `
            <div class="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4">
                <div class="p-6">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4">${title}</h3>
                    <div class="text-gray-600 mb-6">${content}</div>
                    <div class="flex justify-end space-x-3">
                        ${actionButtons}
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        return modalId;
    }
};

// API utilities
const API = {
    base_url: window.location.origin,

    request: async (endpoint, options = {}) => {
        const url = `${API.base_url}/api${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            Toast.show('Request failed. Please try again.', 'error');
            throw error;
        }
    },

    get: (endpoint) => API.request(endpoint),
    post: (endpoint, data) => API.request(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    }),
    put: (endpoint, data) => API.request(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    delete: (endpoint) => API.request(endpoint, {
        method: 'DELETE'
    })
};

// Local storage utilities
const Storage = {
    set: (key, value) => {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            console.error('Failed to save to localStorage:', e);
        }
    },

    get: (key, defaultValue = null) => {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (e) {
            console.error('Failed to read from localStorage:', e);
            return defaultValue;
        }
    },

    remove: (key) => {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.error('Failed to remove from localStorage:', e);
        }
    },

    clear: () => {
        try {
            localStorage.clear();
        } catch (e) {
            console.error('Failed to clear localStorage:', e);
        }
    }
};

// Date/time utilities
const DateUtils = {
    format: (date, format = 'short') => {
        const d = new Date(date);
        
        switch (format) {
            case 'short':
                return d.toLocaleDateString();
            case 'long':
                return d.toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                });
            case 'time':
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            case 'datetime':
                return d.toLocaleString();
            default:
                return d.toLocaleDateString();
        }
    },

    relative: (date) => {
        const now = new Date();
        const past = new Date(date);
        const diffMs = now - past;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        
        return DateUtils.format(date, 'short');
    }
};

// Animation utilities
const Animations = {
    fadeIn: (element, duration = 300) => {
        element.style.opacity = '0';
        element.style.display = 'block';
        
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const opacity = Math.min(progress / duration, 1);
            
            element.style.opacity = opacity;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    },

    fadeOut: (element, duration = 300) => {
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const opacity = Math.max(1 - (progress / duration), 0);
            
            element.style.opacity = opacity;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            } else {
                element.style.display = 'none';
            }
        };
        
        requestAnimationFrame(animate);
    },

    slideIn: (element, direction = 'up', duration = 300) => {
        const transforms = {
            up: 'translateY(20px)',
            down: 'translateY(-20px)',
            left: 'translateX(20px)',
            right: 'translateX(-20px)'
        };
        
        element.style.transform = transforms[direction];
        element.style.opacity = '0';
        element.style.display = 'block';
        
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const easeProgress = 1 - Math.pow(1 - progress / duration, 3);
            
            element.style.transform = `scale(${easeProgress})`;
            element.style.opacity = easeProgress;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            } else {
                element.style.transform = '';
                element.style.opacity = '';
            }
        };
        
        requestAnimationFrame(animate);
    }
};

// Responsive utilities
const Responsive = {
    isMobile: () => window.innerWidth < 768,
    isTablet: () => window.innerWidth >= 768 && window.innerWidth < 1024,
    isDesktop: () => window.innerWidth >= 1024,

    onBreakpointChange: (callback) => {
        let currentBreakpoint = Responsive.isMobile() ? 'mobile' : 
                               Responsive.isTablet() ? 'tablet' : 'desktop';
        
        window.addEventListener('resize', () => {
            const newBreakpoint = Responsive.isMobile() ? 'mobile' : 
                                  Responsive.isTablet() ? 'tablet' : 'desktop';
            
            if (newBreakpoint !== currentBreakpoint) {
                callback(newBreakpoint, currentBreakpoint);
                currentBreakpoint = newBreakpoint;
            }
        });
    }
};

// Debounce utility
const debounce = (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

// Throttle utility
const throttle = (func, limit) => {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
};

// Export utilities for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        FormValidator,
        LoadingManager,
        Toast,
        Modal,
        API,
        Storage,
        DateUtils,
        Animations,
        Responsive,
        debounce,
        throttle
    };
}
