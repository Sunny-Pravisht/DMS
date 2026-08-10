/**
 * Utility functions for safe DOM manipulation and HTML escaping
 */

// CSRF Token Management
let csrfToken = null;

/**
 * Read the CSRF token out of the csrf_token cookie, if present
 * @returns {string|null} CSRF token
 */
function readCSRFTokenFromCookie() {
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrf_token='))
        ?.split('=')[1];

    if (!cookieValue) {
        return null;
    }

    // Extract the actual token from signed cookie
    // The cookie value is in format: token.signature
    return cookieValue.split('.')[0] || null;
}

/**
 * Forget the cached CSRF token so the next request re-reads it
 */
function clearCSRFToken() {
    csrfToken = null;
}

/**
 * Get CSRF token from cookie or fetch from server
 * @param {boolean} forceRefresh - Ignore the cached token
 * @returns {Promise<string>} CSRF token
 */
async function getCSRFToken(forceRefresh = false) {
    if (forceRefresh) {
        csrfToken = null;
    }

    // The cookie is the source of truth for the double-submit pattern: the
    // server verifies the header against the cookie, so a stale cached token
    // (e.g. after the server rotated it) must never win over the live cookie.
    const cookieToken = readCSRFTokenFromCookie();
    if (cookieToken) {
        csrfToken = cookieToken;
        return csrfToken;
    }

    // Check if we have a cached token
    if (csrfToken) {
        return csrfToken;
    }

    // Fetch new token from server
    try {
        const response = await fetch('/api/csrf-token', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            csrfToken = data.csrf_token;
            return csrfToken;
        } else {
            console.error('Failed to fetch CSRF token, response:', response.status);
        }
    } catch (error) {
        console.error('Failed to fetch CSRF token:', error);
    }
    
    return null;
}

/**
 * Add CSRF token to fetch options
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} Updated fetch options with CSRF token
 */
async function addCSRFToken(options = {}) {
    const token = await getCSRFToken();
    
    if (token) {
        options.headers = {
            ...options.headers,
            'X-CSRF-Token': token
        };
        console.debug('CSRF token added to request:', token);
    } else {
        console.warn('No CSRF token available for request');
    }
    
    return options;
}

/**
 * Enhanced fetch with CSRF protection
 * @param {string} url - URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise<Response>} Fetch response
 */
async function secureFetch(url, options = {}) {
    // Only add CSRF token for state-changing methods
    const method = options.method?.toUpperCase() || 'GET';
    
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
        options = await addCSRFToken(options);
    }
    
    // Add credentials for cookie-based auth
    options.credentials = 'include';
    
    return fetch(url, options);
}

/**
 * Escape HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text safe for HTML
 */
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/**
 * Create a DOM element with safe text content
 * @param {string} tagName - HTML tag name
 * @param {string} textContent - Text content (will be escaped)
 * @param {Object} attributes - Element attributes
 * @param {Array} classes - CSS classes to add
 * @returns {HTMLElement} Created element
 */
function createElement(tagName, textContent = '', attributes = {}, classes = []) {
    const element = document.createElement(tagName);
    
    if (textContent) {
        element.textContent = textContent;
    }
    
    Object.entries(attributes).forEach(([key, value]) => {
        if (key === 'data') {
            // Handle data attributes
            Object.entries(value).forEach(([dataKey, dataValue]) => {
                element.dataset[dataKey] = dataValue;
            });
        } else {
            element.setAttribute(key, value);
        }
    });
    
    if (classes.length > 0) {
        element.className = classes.join(' ');
    }
    
    return element;
}

/**
 * Safely set inner HTML with escaped content
 * @param {HTMLElement} element - Target element
 * @param {string} html - HTML content (user data will be escaped)
 * @param {Object} data - Data to interpolate (will be escaped)
 */
function safeInnerHTML(element, html, data = {}) {
    // Replace placeholders with escaped data
    let safeHtml = html;
    
    Object.entries(data).forEach(([key, value]) => {
        const placeholder = new RegExp(`{{${key}}}`, 'g');
        safeHtml = safeHtml.replace(placeholder, escapeHtml(value));
    });
    
    element.innerHTML = safeHtml;
}

/**
 * Create a safe text node
 * @param {string} text - Text content
 * @returns {Text} Text node
 */
function createTextNode(text) {
    return document.createTextNode(text || '');
}

/**
 * Validate and sanitize URL
 * @param {string} url - URL to validate
 * @returns {string|null} Sanitized URL or null if invalid
 */
function sanitizeUrl(url) {
    if (!url) return null;
    
    try {
        const parsed = new URL(url, window.location.origin);
        
        // Only allow http(s) and relative URLs
        if (!['http:', 'https:', ''].includes(parsed.protocol)) {
            return null;
        }
        
        return parsed.href;
    } catch (e) {
        // Try as relative URL
        if (url.startsWith('/')) {
            return url;
        }
        return null;
    }
}

/**
 * Sanitize filename for display
 * @param {string} filename - Filename to sanitize
 * @returns {string} Sanitized filename
 */
function sanitizeFilename(filename) {
    if (!filename) return '';
    
    // Remove any path components
    filename = filename.split('/').pop().split('\\').pop();
    
    // Remove potentially dangerous characters
    return filename.replace(/[<>:"|?*]/g, '_');
}

/**
 * Create safe document card HTML
 * @param {Object} doc - Document object
 * @returns {string} Safe HTML string
 */
function createSafeDocumentCard(doc) {
    const card = createElement('div', '', {}, ['col']);
    const cardInner = createElement('div', '', {}, ['card', 'h-100', 'document-card']);
    
    // Add data attributes
    cardInner.dataset.documentId = doc.id;
    
    // Card body
    const cardBody = createElement('div', '', {}, ['card-body']);
    
    // Title
    const title = createElement('h5', doc.title || 'Untitled', {}, ['card-title']);
    cardBody.appendChild(title);
    
    // Date
    if (doc.document_date) {
        const date = createElement('p', formatDate(doc.document_date), {}, ['text-muted', 'small']);
        cardBody.appendChild(date);
    }
    
    // Summary
    if (doc.summary) {
        const summary = createElement('p', doc.summary, {}, ['card-text']);
        cardBody.appendChild(summary);
    }
    
    // Tags
    if (doc.tags && doc.tags.length > 0) {
        const tagsDiv = createElement('div', '', {}, ['mb-2']);
        doc.tags.forEach(tag => {
            const badge = createElement('span', tag.name, {}, ['badge', 'bg-secondary', 'me-1']);
            tagsDiv.appendChild(badge);
        });
        cardBody.appendChild(tagsDiv);
    }
    
    // Buttons
    const btnGroup = createElement('div', '', {}, ['btn-group', 'btn-group-sm']);
    
    const viewBtn = createElement('button', 'View', {
        type: 'button',
        onclick: `viewDocument('${doc.id}')`
    }, ['btn', 'btn-primary']);
    
    const editBtn = createElement('button', 'Edit', {
        type: 'button',
        onclick: `editDocument('${doc.id}')`
    }, ['btn', 'btn-secondary']);
    
    btnGroup.appendChild(viewBtn);
    btnGroup.appendChild(editBtn);
    cardBody.appendChild(btnGroup);
    
    cardInner.appendChild(cardBody);
    card.appendChild(cardInner);
    
    return card.outerHTML;
}

/**
 * Format date safely
 * @param {string} dateString - Date string to format
 * @returns {string} Formatted date
 */
function formatDate(dateString) {
    if (!dateString) return '';
    
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return '';
        
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch (e) {
        return '';
    }
}

/**
 * Truncate text safely
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated text
 */
function truncateText(text, maxLength = 100) {
    if (!text) return '';
    
    text = String(text);
    if (text.length <= maxLength) return text;
    
    return text.substring(0, maxLength - 3) + '...';
}

/**
 * Create safe alert element
 * @param {string} message - Alert message
 * @param {string} type - Alert type (success, danger, warning, info)
 * @param {boolean} dismissible - Whether alert is dismissible
 * @returns {HTMLElement} Alert element
 */
function createSafeAlert(message, type = 'info', dismissible = true) {
    const alert = createElement('div', '', {
        role: 'alert'
    }, ['alert', `alert-${type}`, dismissible ? 'alert-dismissible' : '', 'fade', 'show']);
    
    // Icon based on type
    const icons = {
        success: 'check-circle',
        danger: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    
    const icon = createElement('i', '', {}, ['fas', `fa-${icons[type] || 'info-circle'}`, 'me-2']);
    alert.appendChild(icon);
    
    // Message
    const messageNode = createTextNode(message);
    alert.appendChild(messageNode);
    
    // Dismiss button
    if (dismissible) {
        const closeBtn = createElement('button', '', {
            type: 'button',
            'data-bs-dismiss': 'alert',
            'aria-label': 'Close'
        }, ['btn-close']);
        alert.appendChild(closeBtn);
    }
    
    return alert;
}

/**
 * Validate search input
 * @param {string} query - Search query
 * @returns {string} Validated query
 */
function validateSearchQuery(query) {
    if (!query) return '';
    
    // Remove potentially dangerous characters
    return query
        .replace(/[<>]/g, '')
        .replace(/javascript:/gi, '')
        .replace(/on\w+\s*=/gi, '')
        .trim();
}

/**
 * Create pagination HTML safely
 * @param {number} currentPage - Current page number
 * @param {number} totalPages - Total number of pages
 * @param {Function} onPageChange - Page change callback
 * @returns {HTMLElement} Pagination element
 */
function createSafePagination(currentPage, totalPages, onPageChange) {
    const nav = createElement('nav', '', {
        'aria-label': 'Page navigation'
    });
    
    const ul = createElement('ul', '', {}, ['pagination', 'justify-content-center']);
    
    // Previous button
    const prevLi = createElement('li', '', {}, ['page-item', currentPage === 1 ? 'disabled' : '']);
    const prevLink = createElement('a', 'Previous', {
        href: '#',
        onclick: (e) => {
            e.preventDefault();
            if (currentPage > 1) onPageChange(currentPage - 1);
        }
    }, ['page-link']);
    prevLi.appendChild(prevLink);
    ul.appendChild(prevLi);
    
    // Page numbers
    const maxButtons = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }
    
    for (let i = startPage; i <= endPage; i++) {
        const li = createElement('li', '', {}, ['page-item', i === currentPage ? 'active' : '']);
        const link = createElement('a', i.toString(), {
            href: '#',
            onclick: (e) => {
                e.preventDefault();
                onPageChange(i);
            }
        }, ['page-link']);
        li.appendChild(link);
        ul.appendChild(li);
    }
    
    // Next button
    const nextLi = createElement('li', '', {}, ['page-item', currentPage === totalPages ? 'disabled' : '']);
    const nextLink = createElement('a', 'Next', {
        href: '#',
        onclick: (e) => {
            e.preventDefault();
            if (currentPage < totalPages) onPageChange(currentPage + 1);
        }
    }, ['page-link']);
    nextLi.appendChild(nextLink);
    ul.appendChild(nextLi);
    
    nav.appendChild(ul);
    return nav;
}