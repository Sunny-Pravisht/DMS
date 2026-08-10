// Search Date Dropdown Functions
function toggleSearchDateDropdown() {
    const dropdown = document.getElementById('search-date-dropdown');
    const display = document.getElementById('selected-search-date-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeSearchReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeSearchDateDropdown() {
    const dropdown = document.getElementById('search-date-dropdown');
    const display = document.getElementById('selected-search-date-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function selectSearchDatePreset(preset) {
    const display = document.getElementById('selected-search-date-display');
    const customDates = document.getElementById('search-custom-dates');
    
    // Update display
    const presetLabels = {
        '': 'All Date Ranges',
        'today': 'Today',
        'yesterday': 'Yesterday',
        'last_7_days': 'Last 7 Days',
        'last_30_days': 'Last 30 Days',
        'last_90_days': 'Last 90 Days',
        'this_week': 'This Week',
        'last_week': 'Last Week',
        'this_month': 'This Month',
        'last_month': 'Last Month',
        'this_quarter': 'This Quarter',
        'last_quarter': 'Last Quarter',
        'this_year': 'This Year',
        'last_year': 'Last Year',
        'custom': 'Custom...'
    };
    
    display.innerHTML = `
        <span>${presetLabels[preset] || 'All Date Ranges'}</span>
        <i class="fas fa-chevron-down ms-auto"></i>
    `;
    
    // Handle custom date inputs
    if (preset === 'custom') {
        customDates.classList.remove('d-none');
    } else {
        customDates.classList.add('d-none');
        document.getElementById('search-date-from').value = '';
        document.getElementById('search-date-to').value = '';
    }
    
    // Update the hidden input value for backward compatibility
    const hiddenInput = document.getElementById('search-date-preset');
    if (hiddenInput) {
        hiddenInput.value = preset;
    }
    
    // Close dropdown
    closeSearchDateDropdown();
    
    // Perform search if there's a query
    if (preset !== 'custom') {
        const query = document.getElementById('search-query').value.trim();
        if (query) {
            performSearch();
        }
    }
}

// Search Reminder Dropdown Functions
function toggleSearchReminderDropdown() {
    const dropdown = document.getElementById('search-reminder-dropdown');
    const display = document.getElementById('selected-search-reminder-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeSearchDateDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeSearchReminderDropdown() {
    const dropdown = document.getElementById('search-reminder-dropdown');
    const display = document.getElementById('selected-search-reminder-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function selectSearchReminderOption(option) {
    const display = document.getElementById('selected-search-reminder-display');
    
    const reminderOptions = {
        'all': 'All Documents',
        'has': 'With Reminder',
        'overdue': 'Overdue Reminders',
        'none': 'Without Reminder'
    };
    
    display.innerHTML = `
        <span>${reminderOptions[option] || 'All Documents'}</span>
        <i class="fas fa-chevron-down ms-auto"></i>
    `;
    
    // Update the hidden input value for backward compatibility
    const hiddenInput = document.getElementById('search-reminder-select');
    if (hiddenInput) {
        hiddenInput.value = option;
    }
    
    // Update the global selectedReminder variable
    if (typeof selectedReminder !== 'undefined') {
        selectedReminder = option;
    }
    
    // Close dropdown
    closeSearchReminderDropdown();
    
    // Perform search
    const query = document.getElementById('search-query').value.trim();
    if (query) {
        performSearch();
    }
}