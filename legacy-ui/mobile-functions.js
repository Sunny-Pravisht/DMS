// Mobile-specific functions for Document Management System

// Toggle mobile search modal
function toggleMobileSearch() {
    const modal = document.getElementById('mobile-search-modal');
    const isShown = modal.classList.contains('show');
    
    if (isShown) {
        closeMobileSearch();
    } else {
        modal.classList.add('show');
        document.getElementById('mobile-search-input').focus();
        document.body.style.overflow = 'hidden'; // Prevent scrolling
    }
}

// Close mobile search
function closeMobileSearch() {
    const modal = document.getElementById('mobile-search-modal');
    modal.classList.remove('show');
    document.body.style.overflow = ''; // Restore scrolling
    document.getElementById('mobile-search-input').value = '';
}

// Perform search from mobile modal
function performMobileSearch() {
    const searchQuery = document.getElementById('mobile-search-input').value;
    if (searchQuery.trim()) {
        // Switch to search tab and populate search field
        showTab('search');
        document.getElementById('search-query').value = searchQuery;
        performSearch();
        closeMobileSearch();
    }
}

// Toggle mobile filters
function toggleMobileFilters() {
    const sidebar = document.getElementById('filter-sidebar');
    const overlay = document.getElementById('mobile-overlay') || createMobileOverlay();
    
    if (sidebar.classList.contains('show')) {
        // Hide filters
        sidebar.classList.remove('show');
        overlay.classList.remove('show');
        document.body.style.overflow = '';
    } else {
        // Show filters
        sidebar.classList.add('show');
        overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
}

// Create overlay for mobile modals
function createMobileOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'mobile-overlay';
    overlay.className = 'mobile-overlay';
    overlay.onclick = toggleMobileFilters;
    document.body.appendChild(overlay);
    return overlay;
}

// Handle mobile search input
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener for mobile search input
    const mobileSearchInput = document.getElementById('mobile-search-input');
    if (mobileSearchInput) {
        mobileSearchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performMobileSearch();
            }
        });
    }
    
    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            // Close mobile modals on resize to desktop
            if (window.innerWidth > 768) {
                closeMobileSearch();
                const sidebar = document.getElementById('filter-sidebar');
                if (sidebar && sidebar.classList.contains('show')) {
                    toggleMobileFilters();
                }
            }
        }, 250);
    });
    
    // Handle escape key for mobile modals
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (document.getElementById('mobile-search-modal').classList.contains('show')) {
                closeMobileSearch();
            }
            const sidebar = document.getElementById('filter-sidebar');
            if (sidebar && sidebar.classList.contains('show') && window.innerWidth <= 768) {
                toggleMobileFilters();
            }
        }
    });
});

// Improved touch handling for document items
function initializeTouchHandlers() {
    if ('ontouchstart' in window) {
        document.addEventListener('touchstart', function(e) {
            if (e.target.closest('.document-item')) {
                e.target.closest('.document-item').classList.add('touch-active');
            }
        });
        
        document.addEventListener('touchend', function(e) {
            if (e.target.closest('.document-item')) {
                setTimeout(() => {
                    e.target.closest('.document-item').classList.remove('touch-active');
                }, 300);
            }
        });
    }
}

// Initialize touch handlers when DOM is ready
document.addEventListener('DOMContentLoaded', initializeTouchHandlers);