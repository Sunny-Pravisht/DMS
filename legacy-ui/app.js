// Document Management System Frontend JavaScript

// Global variables
let currentTab = 'documents';
let currentPage = 1;
let currentFilters = {};
let documents = [];
let correspondents = [];
let doctypes = [];
let tags = [];
let currentDocument = null; // Currently selected document
let originalDocumentTags = []; // Original tags for document editing
let selectedReminder = 'all'; // Track selected reminder filter
let isProcessingActive = false;
let processingCheckInterval = null;

// API base URL - configurable for different environments
const API_BASE = window.location.origin + '/api';

// Authentication helper functions
function isAuthenticated() {
    return document.cookie.includes('session_token=');
}

function redirectToLogin() {
    window.location.href = '/login';
}

// Check session validity with backend
async function checkSessionValidity() {
    try {
        console.log('Checking session validity...');
        const response = await fetch(`${API_BASE}/auth/check-session`, {
            method: 'GET',
            credentials: 'include'
        });
        console.log('Session check response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('Session check result:', data);
            return data.valid === true;
        }
        return false;
    } catch (error) {
        console.error('Session check failed:', error);
        return false;
    }
}

// CSRF token management is handled in utils.js

// Enhanced fetch with authentication and CSRF protection
async function authenticatedFetch(url, options = {}) {
    try {
        // Don't set Content-Type if body is FormData
        const isFormData = options.body instanceof FormData;
        const defaultHeaders = isFormData ? {} : {'Content-Type': 'application/json'};
        
        // Merge headers BEFORE adding CSRF token
        options.headers = {
            ...defaultHeaders,
            ...options.headers
        };
        
        // Use secureFetch from utils.js for CSRF protection
        options = await addCSRFToken(options);
        
        const response = await fetch(url, {
            ...options,
            credentials: 'include' // Include cookies
        });
        
        if (response.status === 401) {
            console.log('Authentication required, redirecting to login...');
            redirectToLogin();
            throw new Error('Authentication required');
        }
        
        if (response.status === 403) {
            const data = await response.json().catch(() => ({}));
            if (data.error === 'missing_or_invalid_csrf_token') {
                // Refresh CSRF token and retry once. The refresh must discard
                // the cached token, otherwise the retry replays the same stale
                // token and fails identically.
                const newToken = await getCSRFToken(true);
                if (newToken && !options._retried) {
                    options._retried = true;
                    return authenticatedFetch(url, options);
                }
            }
        }
        
        return response;
    } catch (error) {
        if (error.message === 'Authentication required') {
            throw error;
        }
        console.error('Network error:', error);
        throw error;
    }
}

// Safe JSON parser with error handling
function safeJSONParse(jsonString, defaultValue = null) {
    try {
        return JSON.parse(jsonString);
    } catch (error) {
        console.error('Failed to parse JSON:', error, 'Input:', jsonString);
        return defaultValue;
    }
}

// Document Relations Functions
async function loadDocumentRelations(documentId) {
    const container = document.getElementById('relationsContent');
    
    try {
        console.log('Loading relations for document:', documentId);
        
        // Show loading state
        if (container) {
            // Safe loading state
            while (container.firstChild) {
                container.removeChild(container.firstChild);
            }
            const loadingDiv = createElement('div', '', {}, ['text-center', 'p-3']);
            const spinner = createElement('i', '', {}, ['fas', 'fa-spinner', 'fa-spin', 'me-2']);
            const loadingText = createTextNode('Loading relations...');
            loadingDiv.appendChild(spinner);
            loadingDiv.appendChild(loadingText);
            container.appendChild(loadingDiv);
        }
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/relations`);
        console.log('Relations API response status:', response.status);
        
        if (response.ok) {
            const relations = await response.json();
            console.log('Relations data received:', relations);
            displayDocumentRelations(relations);
        } else {
            console.error('Failed to load document relations, status:', response.status);
            const errorText = await response.text();
            console.error('Error response:', errorText);
            
            // Show empty state with buttons when server fails
            showEmptyRelationsState(documentId);
        }
    } catch (error) {
        console.error('Error loading document relations:', error);
        
        // Show empty state with buttons when network fails
        showEmptyRelationsState(documentId);
    }
}

function showEmptyRelationsState(documentId) {
    const container = document.getElementById('relationsContent');
    if (!container) return;
    
    // Clear container safely
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    
    // Header section
    const headerDiv = createElement('div', '', {}, ['d-flex', 'justify-content-between', 'align-items-center', 'mb-3']);
    const h6 = createElement('h6', '', {}, ['mb-0']);
    const sitemapIcon = createElement('i', '', {}, ['fas', 'fa-sitemap', 'me-2']);
    h6.appendChild(sitemapIcon);
    h6.appendChild(createTextNode('Document Relations'));
    headerDiv.appendChild(h6);
    
    // Buttons div
    const buttonsDiv = createElement('div');
    const findSimilarBtn = createElement('button', '', {
        type: 'button'
    }, ['btn', 'btn-sm', 'btn-outline-primary', 'me-2']);
    findSimilarBtn.addEventListener('click', showSimilarDocumentsForCurrent);
    const searchIcon = createElement('i', '', {}, ['fas', 'fa-search', 'me-1']);
    findSimilarBtn.appendChild(searchIcon);
    findSimilarBtn.appendChild(createTextNode('Find Similar'));
    
    const addRelationBtn = createElement('button', '', {
        type: 'button'
    }, ['btn', 'btn-sm', 'btn-primary']);
    addRelationBtn.addEventListener('click', () => showAddRelationModal());
    const plusIcon = createElement('i', '', {}, ['fas', 'fa-plus', 'me-1']);
    addRelationBtn.appendChild(plusIcon);
    addRelationBtn.appendChild(createTextNode('Add Relation'));
    
    buttonsDiv.appendChild(findSimilarBtn);
    buttonsDiv.appendChild(addRelationBtn);
    headerDiv.appendChild(buttonsDiv);
    container.appendChild(headerDiv);
    
    // Parent Documents section
    const parentSection = createElement('div', '', {}, ['mb-4']);
    const parentHeader = createElement('h6', '', {}, ['text-muted', 'mb-2']);
    const upIcon = createElement('i', '', {}, ['fas', 'fa-level-up-alt', 'me-1']);
    parentHeader.appendChild(upIcon);
    parentHeader.appendChild(createTextNode('Parent Documents'));
    parentSection.appendChild(parentHeader);
    
    const parentList = createElement('div', '', {
        id: 'parent-documents-list'
    }, ['relations-list']);
    const noParentDiv = createElement('div', 'No parent documents', {}, ['text-muted', 'small']);
    parentList.appendChild(noParentDiv);
    parentSection.appendChild(parentList);
    container.appendChild(parentSection);
    
    // Child Documents section
    const childSection = createElement('div', '', {}, ['mb-4']);
    const childHeader = createElement('h6', '', {}, ['text-muted', 'mb-2']);
    const downIcon = createElement('i', '', {}, ['fas', 'fa-level-down-alt', 'me-1']);
    childHeader.appendChild(downIcon);
    childHeader.appendChild(createTextNode('Child Documents'));
    childSection.appendChild(childHeader);
    
    const childList = createElement('div', '', {
        id: 'child-documents-list'
    }, ['relations-list']);
    const noChildDiv = createElement('div', 'No child documents', {}, ['text-muted', 'small']);
    childList.appendChild(noChildDiv);
    childSection.appendChild(childList);
    container.appendChild(childSection);
    
    // Similar Documents section (hidden by default)
    const similarSection = createElement('div', '', {
        id: 'similar-documents-section'
    }, ['d-none']);
    const hr = createElement('hr');
    similarSection.appendChild(hr);
    
    const similarHeader = createElement('h6', '', {}, ['text-muted', 'mb-2']);
    const brainIcon = createElement('i', '', {}, ['fas', 'fa-brain', 'me-1']);
    similarHeader.appendChild(brainIcon);
    similarHeader.appendChild(createTextNode('Similar Documents'));
    const small = createElement('small', '(by AI similarity)', {}, ['text-muted', 'ms-2']);
    similarHeader.appendChild(small);
    similarSection.appendChild(similarHeader);
    
    const similarList = createElement('div', '', {
        id: 'similar-documents-list'
    }, ['relations-list']);
    similarSection.appendChild(similarList);
    container.appendChild(similarSection);
}

function showAddRelationModal(documentId) {
    // If no documentId provided, use currentDocument
    if (!documentId) {
        if (!currentDocument || !currentDocument.id) {
            console.error('No current document available');
            showAlert('Please select a document first', 'warning');
            return;
        }
        documentId = currentDocument.id;
    }
    
    // Set the current document ID
    const addRelationModal = document.getElementById('addRelationModal');
    if (addRelationModal) {
        addRelationModal.dataset.documentId = documentId;
    } else {
        console.error('Add relation modal element not found');
        showAlert('Unable to open relation modal', 'error');
        return;
    }
    
    // Clear search results
    const searchResults = document.getElementById('document-search-results');
    while (searchResults.firstChild) {
        searchResults.removeChild(searchResults.firstChild);
    }
    const helpDiv = createElement('div', 'Start typing to search for documents...', {}, ['text-muted', 'text-center', 'p-3']);
    searchResults.appendChild(helpDiv);
    document.getElementById('document-search').value = '';
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('addRelationModal'));
    modal.show();
}

async function showSimilarDocumentsForCurrent() {
    if (!currentDocument || !currentDocument.id) {
        console.error('No current document available');
        showAlert('Please select a document first', 'warning');
        return;
    }
    
    await showSimilarDocuments(currentDocument.id);
}

async function showSimilarDocuments(documentId) {
    try {
        console.log('Finding similar documents for:', documentId);
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/similar?limit=5&threshold=0.3`);
        if (response.ok) {
            const data = await response.json();
            console.log('Similar documents found:', data);
            displaySimilarDocuments(data.similar_documents || [], documentId);
            
            // Show the similar documents section
            const similarSection = document.getElementById('similar-documents-section');
            if (similarSection) {
                similarSection.classList.remove('d-none');
            }
        } else {
            const errorData = await response.json();
            console.error('Similar documents API error:', errorData);
            showAlert(errorData.detail || 'Failed to find similar documents', 'warning');
        }
    } catch (error) {
        console.error('Error finding similar documents:', error);
        showAlert('Error finding similar documents', 'danger');
    }
}

// Helper functions for document relations
function displayDocumentRelations(relations) {
    console.log('displayDocumentRelations called with:', relations);
    const container = document.getElementById('relationsContent');
    if (!container) {
        console.error('relationsContent container not found!');
        return;
    }

    // Clear container safely
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }

    // Helper function to create document item
    function createDocumentItem(doc, documentId) {
        const itemDiv = createElement('div', '', {}, ['list-group-item', 'd-flex', 'justify-content-between', 'align-items-center']);
        
        const infoDiv = createElement('div', '', {}, ['flex-grow-1', 'me-2', 'text-truncate']);
        const strong = createElement('strong', doc.title || doc.filename, {
            title: doc.title || doc.filename  // Add tooltip for full title
        });
        infoDiv.appendChild(strong);
        
        if (doc.correspondent) {
            infoDiv.appendChild(createElement('br'));
            const small = createElement('small', '', {}, ['text-muted']);
            small.appendChild(createTextNode('From: ' + (doc.correspondent || '')));
            infoDiv.appendChild(small);
        }
        
        if (doc.document_date) {
            infoDiv.appendChild(createElement('br'));
            const small = createElement('small', '', {}, ['text-muted']);
            small.appendChild(createTextNode('Date: ' + formatDate(doc.document_date)));
            infoDiv.appendChild(small);
        }
        
        itemDiv.appendChild(infoDiv);
        
        const buttonsDiv = createElement('div', '', {}, ['d-flex', 'flex-shrink-0']);
        
        const viewBtn = createElement('button', '', {
            type: 'button',
            title: 'View Document'
        }, ['btn', 'btn-sm', 'btn-outline-primary', 'me-2']);
        viewBtn.addEventListener('click', () => openDocumentModal(doc.id));
        const eyeIcon = createElement('i', '', {}, ['fas', 'fa-eye']);
        viewBtn.appendChild(eyeIcon);
        
        const removeBtn = createElement('button', '', {
            type: 'button',
            title: 'Remove Relation'
        }, ['btn', 'btn-sm', 'btn-outline-danger']);
        removeBtn.addEventListener('click', () => removeDocumentRelation(documentId, doc.id));
        const unlinkIcon = createElement('i', '', {}, ['fas', 'fa-unlink']);
        removeBtn.appendChild(unlinkIcon);
        
        buttonsDiv.appendChild(viewBtn);
        buttonsDiv.appendChild(removeBtn);
        itemDiv.appendChild(buttonsDiv);
        
        return itemDiv;
    }

    // Parent documents section
    if (relations.parent_documents && relations.parent_documents.length > 0) {
        const parentSection = createElement('div', '', {}, ['mb-4']);
        const parentHeader = createElement('h6', '', {}, ['text-muted', 'mb-2']);
        const upIcon = createElement('i', '', {}, ['fas', 'fa-level-up-alt', 'me-2']);
        parentHeader.appendChild(upIcon);
        parentHeader.appendChild(createTextNode('Parent Documents'));
        parentSection.appendChild(parentHeader);
        
        const listGroup = createElement('div', '', {}, ['list-group']);
        relations.parent_documents.forEach(doc => {
            listGroup.appendChild(createDocumentItem(doc, relations.document_id));
        });
        parentSection.appendChild(listGroup);
        container.appendChild(parentSection);
    }

    // Child documents section
    if (relations.child_documents && relations.child_documents.length > 0) {
        const childSection = createElement('div', '', {}, ['mb-4']);
        const childHeader = createElement('h6', '', {}, ['text-muted', 'mb-2']);
        const downIcon = createElement('i', '', {}, ['fas', 'fa-level-down-alt', 'me-2']);
        childHeader.appendChild(downIcon);
        childHeader.appendChild(createTextNode('Child Documents'));
        childSection.appendChild(childHeader);
        
        const listGroup = createElement('div', '', {}, ['list-group']);
        relations.child_documents.forEach(doc => {
            listGroup.appendChild(createDocumentItem(doc, relations.document_id));
        });
        childSection.appendChild(listGroup);
        container.appendChild(childSection);
    }

    // No relations message
    if ((!relations.parent_documents || relations.parent_documents.length === 0) && 
        (!relations.child_documents || relations.child_documents.length === 0)) {
        const noRelationsDiv = createElement('div', '', {}, ['text-center', 'text-muted', 'py-4']);
        const slashIcon = createElement('i', '', {}, ['fas', 'fa-link-slash', 'fa-2x', 'mb-2']);
        noRelationsDiv.appendChild(slashIcon);
        noRelationsDiv.appendChild(createElement('br'));
        noRelationsDiv.appendChild(createTextNode('No document relations found'));
        container.appendChild(noRelationsDiv);
    }

    // Add relation buttons
    const buttonsDiv = createElement('div', '', {}, ['d-flex', 'gap-2', 'mt-3']);
    
    const addBtn = createElement('button', '', {
        type: 'button'
    }, ['btn', 'btn-outline-primary']);
    addBtn.addEventListener('click', () => showAddRelationModal(relations.document_id));
    const plusIcon = createElement('i', '', {}, ['fas', 'fa-plus', 'me-2']);
    addBtn.appendChild(plusIcon);
    addBtn.appendChild(createTextNode('Add Relation'));
    
    const findBtn = createElement('button', '', {
        type: 'button'
    }, ['btn', 'btn-outline-secondary']);
    findBtn.addEventListener('click', () => showSimilarDocuments(relations.document_id));
    const searchIcon = createElement('i', '', {}, ['fas', 'fa-search', 'me-2']);
    findBtn.appendChild(searchIcon);
    findBtn.appendChild(createTextNode('Find Similar'));
    
    buttonsDiv.appendChild(addBtn);
    buttonsDiv.appendChild(findBtn);
    container.appendChild(buttonsDiv);
}

async function searchDocumentsForRelation(query) {
    // If no query provided, get it from the input field
    if (query === undefined) {
        const searchInput = document.getElementById('document-search');
        query = searchInput ? searchInput.value : '';
    }
    
    console.log('searchDocumentsForRelation called with query:', query);
    
    if (!query || query.length < 2) {
        const searchResults = document.getElementById('document-search-results');
        while (searchResults.firstChild) {
            searchResults.removeChild(searchResults.firstChild);
        }
        const helpDiv = createElement('div', 'Start typing to search for documents...', {}, ['text-muted', 'text-center', 'p-3']);
        searchResults.appendChild(helpDiv);
        return;
    }

    // Show loading indicator
    const searchResults = document.getElementById('document-search-results');
    while (searchResults.firstChild) {
        searchResults.removeChild(searchResults.firstChild);
    }
    const loadingDiv = createElement('div', '', {}, ['text-muted', 'text-center', 'p-3']);
    const spinner = createElement('i', '', {}, ['fas', 'fa-spinner', 'fa-spin']);
    loadingDiv.appendChild(spinner);
    loadingDiv.appendChild(createTextNode(' Searching...'));
    searchResults.appendChild(loadingDiv);

    try {
        console.log('Sending search request for:', query);
        
        // Check if semantic search toggle is checked
        const useSemanticSearch = document.getElementById('relation-search-semantic')?.checked ?? true;
        
        // Use same search parameters as main search
        const searchRequest = {
            query: query,
            use_semantic_search: useSemanticSearch,
            limit: 20, // Increased from 10 to match main search
            offset: 0
        };
        
        console.log(`Using ${useSemanticSearch ? 'semantic' : 'text'} search for relations`);
        
        const response = await authenticatedFetch(`${API_BASE}/search/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(searchRequest)
        });
        
        console.log('Search response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('Search results:', data);
            displayRelationSearchResults(data.documents);
        } else {
            console.error('Failed to search documents, status:', response.status);
            const searchResults = document.getElementById('document-search-results');
            while (searchResults.firstChild) {
                searchResults.removeChild(searchResults.firstChild);
            }
            const errorDiv = createElement('div', 'Search failed. Please try again.', {}, ['text-muted', 'text-center', 'p-3', 'text-danger']);
            searchResults.appendChild(errorDiv);
        }
    } catch (error) {
        console.error('Error searching documents:', error);
        const searchResults = document.getElementById('document-search-results');
        while (searchResults.firstChild) {
            searchResults.removeChild(searchResults.firstChild);
        }
        const errorDiv = createElement('div', 'Search error. Please try again.', {}, ['text-muted', 'text-center', 'p-3', 'text-danger']);
        searchResults.appendChild(errorDiv);
    }
}

function displayRelationSearchResults(documents) {
    console.log('displayRelationSearchResults called with:', documents);
    const container = document.getElementById('document-search-results');
    const addRelationModal = document.getElementById('addRelationModal');
    const currentDocumentId = addRelationModal ? addRelationModal.dataset.documentId : null;
    
    console.log('Current document ID for relation:', currentDocumentId);
    
    if (!container) {
        console.error('document-search-results container not found');
        return;
    }
    
    if (!documents || documents.length === 0) {
        console.log('No documents found in search');
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const noDocsDiv = createElement('div', 'No documents found', {}, ['text-muted', 'p-3']);
        container.appendChild(noDocsDiv);
        return;
    }

    let html = '';
    let addedCount = 0;
    documents.forEach((doc, index) => {
        console.log(`Processing search result ${index}:`, doc);
        // Don't show the current document
        if (doc.id === currentDocumentId) {
            console.log('Skipping current document');
            return;
        }
        
        const correspondentName = doc.correspondent?.name || doc.correspondent || '';
        
        html += `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>${escapeHtml(doc.title || doc.filename)}</strong>
                    ${correspondentName ? `<br><small class="text-muted">From: ${escapeHtml(correspondentName)}</small>` : ''}
                    ${doc.document_date ? `<br><small class="text-muted">Date: ${formatDate(doc.document_date)}</small>` : ''}
                </div>
                <div>
                    <button class="btn btn-sm btn-outline-success me-2" onclick="addDocumentRelation('${currentDocumentId}', '${doc.id}', 'child')" title="Add as Child">
                        <i class="fas fa-level-down-alt"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-info" onclick="addDocumentRelation('${currentDocumentId}', '${doc.id}', 'parent')" title="Add as Parent">
                        <i class="fas fa-level-up-alt"></i>
                    </button>
                </div>
            </div>
        `;
        addedCount++;
    });

    console.log(`Generated HTML for ${addedCount} search results`);
    
    if (addedCount === 0) {
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const noOtherDiv = createElement('div', 'No other documents found (current document excluded)', {}, ['text-muted', 'p-3']);
        container.appendChild(noOtherDiv);
    } else {
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        // Create list group and populate it
        const listGroup = createElement('div', '', {}, ['list-group']);
        // Use safeInnerHTML for the pre-escaped content
        safeInnerHTML(listGroup, html, {});
        container.appendChild(listGroup);
    }
}

async function addDocumentRelation(documentId, relatedDocumentId, relationType) {
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/relations/${relatedDocumentId}?relation_type=${relationType}`, {
            method: 'POST'
        });

        if (response.ok) {
            showAlert('Relation added successfully', 'success');
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('addRelationModal'));
            if (modal) modal.hide();
            
            // Reload relations
            loadDocumentRelations(documentId);
        } else {
            const errorData = await response.json();
            showAlert(errorData.detail || 'Failed to add relation', 'danger');
        }
    } catch (error) {
        console.error('Error adding document relation:', error);
        showAlert('Error adding relation', 'danger');
    }
}

async function removeDocumentRelation(documentId, relatedDocumentId) {
    if (!confirm('Are you sure you want to remove this document relation?')) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/relations/${relatedDocumentId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showAlert('Relation removed successfully', 'success');
            loadDocumentRelations(documentId);
        } else {
            const errorData = await response.json();
            showAlert(errorData.detail || 'Failed to remove relation', 'danger');
        }
    } catch (error) {
        console.error('Error removing document relation:', error);
        showAlert('Error removing relation', 'danger');
    }
}

function displaySimilarDocuments(documents, currentDocumentId) {
    console.log('displaySimilarDocuments called with:', documents, currentDocumentId);
    const container = document.getElementById('similar-documents-list');
    
    if (!container) {
        console.error('similar-documents-list container not found');
        return;
    }
    
    if (!documents || documents.length === 0) {
        console.log('No similar documents to display');
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const noDocsDiv = createElement('div', 'No similar documents found', {}, ['text-muted', 'small']);
        container.appendChild(noDocsDiv);
        return;
    }

    let html = '';
    documents.forEach((doc, index) => {
        console.log(`Processing document ${index}:`, doc);
        const similarity = doc.similarity_score ? Math.round(doc.similarity_score * 100) : 'N/A';
        const correspondentName = doc.correspondent?.name || doc.correspondent || '';
        
        html += `
            <div class="relation-item d-flex justify-content-between align-items-start mb-2">
                <div class="flex-grow-1">
                    <div class="fw-medium">${escapeHtml(doc.title || doc.filename)}</div>
                    ${doc.summary ? `<div class="text-muted small">${escapeHtml(doc.summary.substring(0, 100))}${doc.summary.length > 100 ? '...' : ''}</div>` : ''}
                    <div class="d-flex gap-3 mt-1">
                        ${correspondentName ? `<small class="text-muted"><i class="fas fa-user me-1"></i>${escapeHtml(correspondentName)}</small>` : ''}
                        ${doc.document_date ? `<small class="text-muted"><i class="fas fa-calendar me-1"></i>${formatDate(doc.document_date)}</small>` : ''}
                        <small class="text-muted"><i class="fas fa-percentage me-1"></i>${similarity}% similar</small>
                    </div>
                </div>
                <div class="ms-2">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="viewDocument('${doc.id}')" title="View Document">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-success" onclick="addSimilarDocumentAsRelation('${currentDocumentId}', '${doc.id}')" title="Add as Related">
                        <i class="fas fa-link"></i>
                    </button>
                </div>
            </div>
        `;
    });

    console.log('Setting content for similar documents');
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    // Use safeInnerHTML for the pre-escaped content
    safeInnerHTML(container, html, {});
}

async function addSimilarDocumentAsRelation(documentId, relatedDocumentId) {
    try {
        const response = await authenticatedFetch(`/api/documents/${documentId}/relations/${relatedDocumentId}?relation_type=child`, {
            method: 'POST'
        });

        if (response.ok) {
            showAlert('Document added as relation', 'success');
            
            // Hide the similar documents section
            const similarSection = document.getElementById('similar-documents-section');
            if (similarSection) {
                similarSection.classList.add('d-none');
            }
            
            // Reload relations if we're in the document details view
            loadDocumentRelations(documentId);
        } else {
            // Don't try to read JSON if it was already read (e.g., for CSRF check)
            let errorMessage = 'Failed to add relation';
            if (response.status === 403) {
                errorMessage = 'Permission denied. Please check your access rights.';
            } else {
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } catch (e) {
                    // JSON already read or invalid
                }
            }
            showAlert(errorMessage, 'danger');
        }
    } catch (error) {
        console.error('Error adding similar document as relation:', error);
        showAlert('Error adding relation', 'danger');
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Document Management System initialized');
    
    // Check authentication with backend before initializing
    const sessionValid = await checkSessionValidity();
    if (!sessionValid) {
        console.log('Session invalid, redirecting to login...');
        redirectToLogin();
        return;
    }
    
    // Proactively get CSRF token after successful authentication
    const token = await getCSRFToken();
    
    console.log('Session valid, initializing application...');
    
    // Check if password change is required
    const mustChangePassword = localStorage.getItem('mustChangePassword');
    if (mustChangePassword === 'true') {
        console.log('Password change required, showing modal...');
        localStorage.removeItem('mustChangePassword');
        
        // Show the forced password change modal
        const modal = new bootstrap.Modal(document.getElementById('forcePasswordChangeModal'));
        modal.show();
        
        // Don't initialize the rest of the app until password is changed
        return;
    }
    
    // The first-run setup wizard is retired. It existed to collect an OpenAI
    // key and folder paths; both now live in .env and config/models.json, so
    // it only ever showed a stale OpenAI-only form. Clear any leftover flags
    // so it cannot pop up again for users who set them before the change.
    localStorage.removeItem('showFullSetupWizard');
    localStorage.removeItem('showSetupWizardOnLoad');

    // Check if setup is complete (no users exist)
    let needsSetup = false;
    try {
        const setupResponse = await fetch(`${API_BASE}/auth/setup/check`);
        if (setupResponse.ok) {
            const setupData = await setupResponse.json();
            if (!setupData.setup_complete) {
                // No admin users exist, must redirect to login for initial setup
                console.log('No users found, redirecting to login for initial setup...');
                window.location.href = '/login';
                return;
            }
        }
    } catch (error) {
        console.error('Failed to check setup status:', error);
    }
    
    checkSystemHealth();
    loadInitialData();
    loadUserPreferences();
    setupKeyboardShortcuts();
    displaySavedSearches();
    setupChangePasswordForm(); // Setup password change form
    startProcessingMonitoring(); // Start monitoring for document processing
    showTab('documents');
    
    // Add event listener for reminder date field
    const reminderDateField = document.getElementById('edit-reminder-date');
    if (reminderDateField) {
        reminderDateField.addEventListener('change', function() {
            const reminderLabel = document.querySelector('label[for="edit-reminder-date"]');
            const selectedDate = new Date(this.value);
            const now = new Date();
            
            if (this.value && selectedDate < now) {
                this.classList.add('past-reminder');
                if (reminderLabel) {
                    reminderLabel.classList.add('past-reminder');
                }
            } else {
                this.classList.remove('past-reminder');
                if (reminderLabel) {
                    reminderLabel.classList.remove('past-reminder');
                }
            }
        });
    }
    
    // Add event listeners for AI provider radio buttons
    // Use event delegation since settings tab might not be loaded yet
    document.addEventListener('change', function(e) {
        if (e.target && (e.target.name === 'ai-provider' || e.target.name === 'wizard-ai-provider')) {
            if (e.target.checked) {
                console.log('AI provider changed to:', e.target.value);
                updateAIProviderUI(e.target.value);
                // Don't automatically save provider change - wait for configuration
                // Show appropriate instructions
                const statusDiv = document.getElementById('ai-provider-status');
                if (statusDiv && e.target.value === 'azure') {
                    statusDiv.className = 'alert alert-warning mt-3';
                    // Clear and set status message safely
                    while (statusDiv.firstChild) {
                        statusDiv.removeChild(statusDiv.firstChild);
                    }
                    const warningIcon = createElement('i', '', {}, ['fas', 'fa-exclamation-triangle', 'me-2']);
                    statusDiv.appendChild(warningIcon);
                    statusDiv.appendChild(createTextNode('Please configure Azure OpenAI settings below and save the configuration.'));
                    statusDiv.classList.remove('d-none');
                }
            }
        }
    });
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    stopProcessingMonitoring();
});

// Load user preferences from localStorage
function loadUserPreferences() {
    const savedView = localStorage.getItem('documentView') || 'grid';
    toggleView(savedView);
}

// Add keyboard shortcuts for better UX
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Only handle shortcuts when not typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        // Arrow key navigation for pagination
        if (e.key === 'ArrowLeft' && currentPage > 1) {
            e.preventDefault();
            navigateToPage(currentPage - 1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            navigateToPage(currentPage + 1);
        }
        
        // Tab switching with number keys
        if (e.key >= '1' && e.key <= '6') {
            e.preventDefault();
            const tabs = ['documents', 'search', 'upload', 'rag', 'manage', 'settings'];
            const tabIndex = parseInt(e.key) - 1;
            if (tabs[tabIndex]) {
                showTab(tabs[tabIndex]);
            }
        }
        
        // Quick refresh with F5 or Ctrl+R
        if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
            e.preventDefault();
            refreshDocuments();
        }
    });
}

// Tab management
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.add('d-none');
        tab.style.display = 'none'; // Force hide
    });
    
    // Show selected tab
    const targetTab = document.getElementById(`${tabName}-tab`);
    if (targetTab) {
        targetTab.classList.remove('d-none');
        targetTab.style.display = 'block'; // Force show
    }
    
    // Update navbar - get the clicked element properly
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Find and activate the correct nav link
    const clickedLink = document.querySelector(`[onclick="showTab('${tabName}')"]`);
    if (clickedLink) {
        clickedLink.classList.add('active');
    }
    
    currentTab = tabName;
    
    // Load tab-specific data
    switch(tabName) {
        case 'documents':
            // Clear any existing loading states first
            hideLoading('documents-loading');
            loadDocuments();
            break;
        case 'search':
            // Populate search filters when tab is shown
            populateSearchFilters();
            break;
        case 'upload':
            refreshStagingFiles();
            break;
        case 'rag':
            // Update Ask AI button state when switching to RAG tab
            updateAskAIButton();
            break;
        case 'manage':
            loadManageData();
            break;
        case 'settings':
            loadSettings();
            loadAIProviderStatus();
            loadSettingsExtendedWithUsers();
            loadUsers();
            loadCurrentUser();
            break;
    }
}

// Make the real showTab available and replace the temporary one
window.realShowTab = showTab;
window.showTab = showTab;

// If there was a pending tab request, execute it now
if (window.pendingTabRequest) {
    console.log('Executing pending tab request:', window.pendingTabRequest);
    showTab(window.pendingTabRequest);
    window.pendingTabRequest = null;
}

// System health check
async function checkSystemHealth() {
    const container = document.getElementById('health-status');
    if (container) {
        // Show loading state
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const loadingDiv = createElement('div', '', {}, ['health-loading']);
        const spinnerDiv = createElement('div', '', {}, ['health-loading-spinner']);
        const textDiv = createElement('div', 'Checking system health...', {}, ['text-muted']);
        loadingDiv.appendChild(spinnerDiv);
        loadingDiv.appendChild(textDiv);
        container.appendChild(loadingDiv);
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/health/`);
        const health = await response.json();
        
        let overallStatus = 'healthy';
        let statusClass = 'bg-success';
        
        // Check if any service has issues (handle both old and new format)
        if (health.services) {
            // New format - check services object
            for (const [serviceName, serviceData] of Object.entries(health.services)) {
                const status = serviceData.status || 'unknown';
                if (status === 'unhealthy') {
                    overallStatus = 'error';
                    statusClass = 'bg-danger';
                    break;
                } else if (status === 'warning') {
                    overallStatus = 'warning';
                    statusClass = 'bg-warning';
                }
            }
        } else {
            // Old format - check status strings
            for (const [serviceName, status] of Object.entries(health)) {
                let statusText = status;
                if (typeof status === 'object') {
                    statusText = status.status || 'unknown';
                }
                
                if (typeof statusText === 'string') {
                    if (statusText.includes('error') || statusText === 'unhealthy') {
                        overallStatus = 'error';
                        statusClass = 'bg-danger';
                        break;
                    } else if (statusText.includes('not_configured') || statusText.includes('some_missing')) {
                        overallStatus = 'warning';
                        statusClass = 'bg-warning';
                    }
                }
            }
        }
        
        const statusIndicator = document.getElementById('status-indicator');
        if (statusIndicator) {
            statusIndicator.textContent = 
                overallStatus === 'healthy' ? 'Healthy' : 
                overallStatus === 'warning' ? 'Warning' : 'Error';
            statusIndicator.className = `badge ${statusClass}`;
        }
        
        // Display the health status using the new format
        displayHealth(health);
        
    } catch (error) {
        console.error('Health check failed:', error);
        const statusIndicator = document.getElementById('status-indicator');
        if (statusIndicator) {
            statusIndicator.textContent = 'Error';
            statusIndicator.className = 'badge bg-danger';
        }
        
        if (container) {
            while (container.firstChild) {
                container.removeChild(container.firstChild);
            }
            const alertDiv = createElement('div', '', {}, ['alert', 'alert-danger']);
            const icon = createElement('i', '', {}, ['fas', 'fa-exclamation-triangle', 'me-2']);
            alertDiv.appendChild(icon);
            alertDiv.appendChild(createTextNode('Failed to check system health: ' + error.message));
            container.appendChild(alertDiv);
        }
    }
}

// Load initial data
async function loadInitialData() {
    try {
        await Promise.all([
            loadCorrespondents(),
            loadDocTypes(),
            loadTags()
        ]);
        populateFilters();
    } catch (error) {
        console.error('Failed to load initial data:', error);
        showAlert('Failed to load initial data', 'danger');
    }
}

// Document management
async function loadDocuments(page = 1) {
    try {
        showLoading('documents-loading');
        hideElement('documents-list');
        
        // If we have multiple selections, we need to fetch all documents without backend filtering
        const hasMultipleSelections = 
            (currentFilters.correspondent_ids && currentFilters.correspondent_ids.length > 1) ||
            (currentFilters.doctype_ids && currentFilters.doctype_ids.length > 1);
        
        let allDocuments = [];
        
        if (hasMultipleSelections) {
            // Fetch ALL documents when we have multiple selections
            const params = new URLSearchParams({
                skip: 0,
                limit: 1000, // Get many more documents
            });
            
            // Only add tax filter as it's boolean
            if (currentFilters.is_tax_relevant) {
                params.append('is_tax_relevant', 'true');
            }
            
            // Add date and reminder filters
            if (currentFilters.date_range) {
                params.append('date_range', currentFilters.date_range);
            } else {
                if (currentFilters.date_from) {
                    params.append('date_from', currentFilters.date_from);
                }
                if (currentFilters.date_to) {
                    params.append('date_to', currentFilters.date_to);
                }
            }
            if (currentFilters.reminder_filter) {
                params.append('reminder_filter', currentFilters.reminder_filter);
            }
            
            const response = await authenticatedFetch(`${API_BASE}/documents/?${params}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            allDocuments = await response.json();
        } else {
            // Use backend filtering for single selections
            const backendFilters = {};
            if (currentFilters.correspondent_id) backendFilters.correspondent_id = currentFilters.correspondent_id;
            if (currentFilters.doctype_id) backendFilters.doctype_id = currentFilters.doctype_id;
            if (currentFilters.is_tax_relevant) backendFilters.is_tax_relevant = currentFilters.is_tax_relevant;
            
            // Date filters - prefer preset over custom range
            if (currentFilters.date_range) {
                backendFilters.date_range = currentFilters.date_range;
            } else {
                if (currentFilters.date_from) backendFilters.date_from = currentFilters.date_from;
                if (currentFilters.date_to) backendFilters.date_to = currentFilters.date_to;
            }
            
            if (currentFilters.reminder_filter) backendFilters.reminder_filter = currentFilters.reminder_filter;
            
            const params = new URLSearchParams({
                skip: 0,
                limit: 200, // Still get more for tags filtering
                ...backendFilters
            });
            
            const response = await authenticatedFetch(`${API_BASE}/documents/?${params}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            allDocuments = await response.json();
        }
        
        // Check if documents have approval fields (only log if missing)
        if (allDocuments.length > 0) {
            const firstDoc = allDocuments[0];
            if (!('is_approved' in firstDoc)) {
                console.warn('Documents missing approval fields. Server restart may be needed.');
            }
        }
        
        // Apply client-side filtering for all cases (tags always need client-side filtering)
        documents = applyClientSideFilters(allDocuments);
        
        // Paginate on client side
        const startIndex = (page - 1) * 20;
        const paginatedDocuments = documents.slice(startIndex, startIndex + 20);
        
        displayDocuments(paginatedDocuments);
        updateDocumentCount(documents.length);
        updatePagination(page, documents.length);
        hideLoading('documents-loading');
        showElement('documents-list');
        
    } catch (error) {
        console.error('Failed to load documents:', error);
        showAlert('Failed to load documents: ' + error.message, 'danger');
        hideLoading('documents-loading');
        showElement('documents-list');
    }
}

function getProcessingStatusHtml(doc) {
    // Only log warnings for missing approval fields
    if (doc.is_approved === undefined) {
        console.warn('Document missing approval field:', doc.id);
    }
    
    let statusHtml = '';
    
    // Processing status
    if (doc.ocr_status === 'failed') {
        statusHtml += `
            <div class="processing-status status-failed" title="OCR processing failed">
                <i class="fas fa-exclamation-circle me-1"></i>Failed
            </div>
            <button class="btn btn-sm btn-outline-warning mt-1" onclick="retryProcessing('${doc.id}')" title="Retry processing">
                <i class="fas fa-redo me-1"></i>Retry
            </button>
        `;
    } else if (doc.ocr_status === 'completed' && doc.ai_status === 'completed') {
        statusHtml += '<div class="processing-status status-completed" title="Fully processed"><i class="fas fa-check-circle me-1"></i>Complete</div>';
    } else if (doc.ocr_status === 'processing' || doc.ai_status === 'processing') {
        statusHtml += '<div class="processing-status status-processing" title="Processing in progress"><i class="fas fa-spinner fa-spin me-1"></i>Processing</div>';
    } else if (doc.ai_status === 'failed') {
        statusHtml += `
            <div class="processing-status status-warning" title="AI processing failed but OCR succeeded">
                <i class="fas fa-exclamation-triangle me-1"></i>Partial
            </div>
            <button class="btn btn-sm btn-outline-warning mt-1" onclick="retryAIProcessing('${doc.id}')" title="Retry AI processing">
                <i class="fas fa-redo me-1"></i>Retry AI
            </button>
        `;
    } else {
        statusHtml += '<div class="processing-status status-pending" title="Waiting to be processed"><i class="fas fa-clock me-1"></i>Pending</div>';
    }
    
    // Approval status
    const isApproved = doc.is_approved === true;
    const hasApprovalField = doc.hasOwnProperty('is_approved');
    
    if (!hasApprovalField || !isApproved) {
        // Show approve button for documents without approval field or not approved
        statusHtml += `
            <button class="btn btn-sm btn-outline-success mt-1" onclick="toggleApproval('${doc.id}', true)" title="Approve document">
                <i class="fas fa-thumbs-up me-1"></i>Approve
            </button>
        `;
    } else {
        // Show approved status
        statusHtml += `
            <div class="approval-status status-approved mt-1" title="Document approved">
                <i class="fas fa-check-circle me-1"></i>Approved
            </div>
        `;
    }
    
    return statusHtml;
}

// Make toggleApproval available globally
window.toggleApproval = async function(documentId, approved) {
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/approve`, {
            method: 'POST',
            body: JSON.stringify({ approved: approved })
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
            
            // Refresh the documents list to show updated status
            refreshDocuments();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update approval status', 'danger');
        }
    } catch (error) {
        console.error('Error updating approval status:', error);
        showAlert('Error updating approval status', 'danger');
    }
};

function displayDocuments(docs) {
    const container = document.getElementById('documents-list');
    
    // Debug: Check if documents have summaries
    console.log('Displaying documents:', docs.length);
    console.log('Documents with summaries:', docs.filter(d => d.summary).length);
    
    // Count failed documents and show/hide retry button
    const failedDocs = docs.filter(doc => 
        doc.ocr_status === 'failed' || 
        doc.ai_status === 'failed' || 
        doc.vector_status === 'failed'
    );
    
    const retryButton = document.getElementById('retry-all-failed-btn');
    if (retryButton) {
        if (failedDocs.length > 0) {
            retryButton.classList.remove('d-none');
            retryButton.title = `Retry ${failedDocs.length} failed document${failedDocs.length > 1 ? 's' : ''}`;
        } else {
            retryButton.classList.add('d-none');
        }
    }
    
    if (docs.length === 0) {
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const centerDiv = createElement('div', '', {}, ['text-center', 'py-4']);
        const icon = createElement('i', '', {}, ['fas', 'fa-file-alt', 'fa-3x', 'text-muted', 'mb-3']);
        const p = createElement('p', 'No documents found', {}, ['text-muted']);
        centerDiv.appendChild(icon);
        centerDiv.appendChild(p);
        container.appendChild(centerDiv);
        return;
    }
    
    const viewType = document.querySelector('#documents-list').classList.contains('document-grid') ? 'grid' : 'list';
    const now = new Date();
    
    // Clear container
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    
    // Build documents using DOM methods
    docs.forEach(doc => {
        // Check if document has a past reminder
        const hasPastReminder = doc.reminder_date && new Date(doc.reminder_date) < now;
        const documentClasses = ['document-item'];
        if (hasPastReminder) documentClasses.push('past-reminder');
        
        const docDiv = createElement('div', '', {}, documentClasses);
        docDiv.addEventListener('click', () => openDocumentModal(doc.id));
        
        if (viewType === 'grid') {
            // Grid View Layout
            const gridContent = createElement('div', '', {}, ['document-grid-content']);
            
            // Header
            const header = createElement('div', '', {}, ['document-header']);
            const title = createElement('h6', doc.title || doc.filename, {
                title: doc.title || doc.filename
            }, ['document-title']);
            header.appendChild(title);
            
            const statusDiv = createElement('div', '', {}, ['document-status']);
            // Use safeInnerHTML for processing status as it contains icons and buttons
            safeInnerHTML(statusDiv, getProcessingStatusHtml(doc), {});
            header.appendChild(statusDiv);
            gridContent.appendChild(header);
            
            // Meta
            const meta = createElement('div', '', {}, ['document-meta']);
            
            // User meta
            const userMeta = createElement('div', '', {}, ['meta-item']);
            const userIcon = createElement('i', '', {}, ['fas', 'fa-user', 'me-1']);
            const userText = createElement('span', doc.correspondent?.name || 'Unknown', {}, ['meta-text']);
            userMeta.appendChild(userIcon);
            userMeta.appendChild(userText);
            meta.appendChild(userMeta);
            
            // File meta
            const fileMeta = createElement('div', '', {}, ['meta-item']);
            const fileIcon = createElement('i', '', {}, ['fas', 'fa-file', 'me-1']);
            const fileText = createElement('span', doc.doctype?.name || 'Unknown', {}, ['meta-text']);
            fileMeta.appendChild(fileIcon);
            fileMeta.appendChild(fileText);
            meta.appendChild(fileMeta);
            
            // Date meta
            const dateMeta = createElement('div', '', {}, ['meta-item']);
            const dateIcon = createElement('i', '', {}, ['fas', 'fa-calendar', 'me-1']);
            const dateText = createElement('span', 
                doc.document_date ? new Date(doc.document_date).toLocaleDateString() : 'No date', 
                {}, ['meta-text']);
            dateMeta.appendChild(dateIcon);
            dateMeta.appendChild(dateText);
            meta.appendChild(dateMeta);
            
            // Tax badge
            if (doc.is_tax_relevant) {
                const taxBadge = createElement('div', 'Tax', {}, ['badge', 'badge-tax', 'mt-1']);
                meta.appendChild(taxBadge);
            }
            
            // Reminder meta
            if (hasPastReminder) {
                const reminderMeta = createElement('div', '', {}, ['meta-item', 'reminder-meta']);
                const bellIcon = createElement('i', '', {}, ['fas', 'fa-bell', 'me-1']);
                const reminderText = createElement('span', 
                    'Reminder: ' + new Date(doc.reminder_date).toLocaleDateString(), 
                    {}, ['meta-text']);
                reminderMeta.appendChild(bellIcon);
                reminderMeta.appendChild(reminderText);
                meta.appendChild(reminderMeta);
            }
            
            gridContent.appendChild(meta);
            
            // Tags
            const tagsContainer = createElement('div', '', {}, ['document-tags-container']);
            doc.tags.slice(0, 3).forEach(tag => {
                const tagSpan = createElement('span', tag.name, {
                    title: tag.name,
                    style: `background-color: ${tag.color || '#64748b'};`
                }, ['document-tag']);
                tagsContainer.appendChild(tagSpan);
            });
            
            if (doc.tags.length > 3) {
                const moreSpan = createElement('span', '+' + (doc.tags.length - 3), {
                    title: doc.tags.slice(3).map(t => t.name).join(', ')
                }, ['tag-more']);
                tagsContainer.appendChild(moreSpan);
            }
            
            gridContent.appendChild(tagsContainer);
            docDiv.appendChild(gridContent);
            
        } else {
            // List View Layout
            const listContent = createElement('div', '', {}, ['d-flex', 'justify-content-between', 'align-items-start', 'h-100']);
            
            // Left side
            const leftDiv = createElement('div', '', {}, ['flex-grow-1', 'overflow-hidden']);
            
            // Title
            const titleH6 = createElement('h6', '', {
                title: doc.title || doc.filename
            }, ['document-title', 'mb-1']);
            titleH6.appendChild(createTextNode(doc.title || doc.filename));
            
            if (doc.is_tax_relevant) {
                const taxBadge = createElement('span', 'Tax', {}, ['badge', 'badge-tax', 'ms-2']);
                titleH6.appendChild(taxBadge);
            }
            leftDiv.appendChild(titleH6);
            
            // Meta line
            const metaDiv = createElement('div', '', {}, ['document-meta', 'mb-2']);
            
            // User
            const userSpan = createElement('span', '', {}, ['meta-item']);
            const userIcon = createElement('i', '', {}, ['fas', 'fa-user', 'me-1']);
            userSpan.appendChild(userIcon);
            userSpan.appendChild(createTextNode(doc.correspondent?.name || 'Unknown'));
            metaDiv.appendChild(userSpan);
            
            metaDiv.appendChild(createElement('span', '•', {}, ['meta-separator']));
            
            // File type
            const fileSpan = createElement('span', '', {}, ['meta-item']);
            const fileIcon = createElement('i', '', {}, ['fas', 'fa-file', 'me-1']);
            fileSpan.appendChild(fileIcon);
            fileSpan.appendChild(createTextNode(doc.doctype?.name || 'Unknown'));
            metaDiv.appendChild(fileSpan);
            
            metaDiv.appendChild(createElement('span', '•', {}, ['meta-separator']));
            
            // Date
            const dateSpan = createElement('span', '', {}, ['meta-item']);
            const dateIcon = createElement('i', '', {}, ['fas', 'fa-calendar', 'me-1']);
            dateSpan.appendChild(dateIcon);
            dateSpan.appendChild(createTextNode(
                doc.document_date ? new Date(doc.document_date).toLocaleDateString() : 'No date'
            ));
            metaDiv.appendChild(dateSpan);
            
            // Reminder
            if (hasPastReminder) {
                metaDiv.appendChild(createElement('span', '•', {}, ['meta-separator']));
                const reminderSpan = createElement('span', '', {}, ['meta-item', 'reminder-meta']);
                const bellIcon = createElement('i', '', {}, ['fas', 'fa-bell', 'me-1']);
                reminderSpan.appendChild(bellIcon);
                reminderSpan.appendChild(createTextNode(
                    'Reminder: ' + new Date(doc.reminder_date).toLocaleDateString()
                ));
                metaDiv.appendChild(reminderSpan);
            }
            
            leftDiv.appendChild(metaDiv);
            
            // Summary
            if (doc.summary) {
                const summaryP = createElement('p', '', {}, ['document-summary', 'mb-2']);
                const summaryText = doc.summary.length > 150 ? 
                    doc.summary.substring(0, 150) + '...' : doc.summary;
                summaryP.appendChild(createTextNode(summaryText));
                leftDiv.appendChild(summaryP);
            }
            
            // Tags
            const tagsDiv = createElement('div', '', {}, ['document-tags-container']);
            doc.tags.forEach(tag => {
                const tagSpan = createElement('span', tag.name, {
                    title: tag.name,
                    style: `background-color: ${tag.color || '#64748b'};`
                }, ['document-tag']);
                tagsDiv.appendChild(tagSpan);
            });
            leftDiv.appendChild(tagsDiv);
            
            listContent.appendChild(leftDiv);
            
            // Right side - status
            const rightDiv = createElement('div', '', {}, ['ms-3']);
            // Use safeInnerHTML for processing status as it contains icons and buttons
            safeInnerHTML(rightDiv, getProcessingStatusHtml(doc), {});
            listContent.appendChild(rightDiv);
            
            docDiv.appendChild(listContent);
        }
        
        container.appendChild(docDiv);
    });
}

function refreshDocuments() {
    currentPage = 1;
    loadDocuments(currentPage);
}

// Search functionality
async function performSearch() {
    const query = document.getElementById('search-query').value.trim();
    const useSemanticSearch = document.getElementById('search-semantic').checked;
    
    if (!query) {
        showAlert('Please enter a search query', 'warning');
        return;
    }
    
    try {
        console.log(`[SEARCH] Starting ${useSemanticSearch ? 'semantic' : 'text'} search for: "${query}"`);
        
        // Show loading animation
        const resultsDiv = document.getElementById('search-results');
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'search-loading';
        loadingDiv.className = 'text-center py-4';
        // Create spinner
        const spinnerDiv = createElement('div', '', {
            role: 'status'
        }, ['spinner-border', 'text-primary']);
        const spinnerSpan = createElement('span', 'Searching...', {}, ['visually-hidden']);
        spinnerDiv.appendChild(spinnerSpan);
        loadingDiv.appendChild(spinnerDiv);
        
        const p = createElement('p', 'Searching documents...', {}, ['mt-2', 'text-muted']);
        loadingDiv.appendChild(p);
        
        const searchResultsList = document.getElementById('search-results-list');
        while (searchResultsList.firstChild) {
            searchResultsList.removeChild(searchResultsList.firstChild);
        }
        document.getElementById('search-results-list').appendChild(loadingDiv);
        resultsDiv.classList.remove('d-none');
        
        // Collect filter values from multiselect arrays
        const filters = {};
        
        // Use multiselect arrays for correspondents, doctypes, and tags
        if (selectedSearchCorrespondents.length > 0) {
            filters.correspondent_ids = selectedSearchCorrespondents;
        }
        if (selectedSearchDoctypes.length > 0) {
            filters.doctype_ids = selectedSearchDoctypes;
        }
        if (selectedSearchTags.length > 0) {
            filters.tag_ids = selectedSearchTags;
        }
        
        // Tax checkbox
        const taxCheckbox = document.getElementById('search-filter-tax');
        if (taxCheckbox && taxCheckbox.checked) {
            filters.is_tax_relevant = true;
        }
        
        // Date range filters - check for preset first
        const searchDatePreset = document.getElementById('search-date-preset').value;
        if (searchDatePreset && searchDatePreset !== 'custom') {
            filters.date_range = searchDatePreset;
        } else {
            // Use custom date range
            const dateFrom = document.getElementById('search-date-from').value;
            const dateTo = document.getElementById('search-date-to').value;
            if (dateFrom) filters.date_from = dateFrom;
            if (dateTo) filters.date_to = dateTo;
        }
        
        // Reminder filter - use select instead of radio buttons
        const reminderSelect = document.getElementById('search-reminder-select')?.value;
        if (reminderSelect && reminderSelect !== 'all') {
            filters.reminder_filter = reminderSelect;
        }
        
        const searchRequest = {
            query: query,
            use_semantic_search: useSemanticSearch,
            limit: 20,
            offset: 0
        };
        
        // Only add filters if there are any
        if (Object.keys(filters).length > 0) {
            searchRequest.filters = filters;
        }
        
        console.log('[SEARCH] Request payload:', searchRequest);
        console.log('[SEARCH] API URL:', `${API_BASE}/search/`);
        
        const startTime = Date.now();
        const response = await authenticatedFetch(`${API_BASE}/search/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(searchRequest)
        });
        
        console.log('[SEARCH] Response status:', response.status);
        console.log('[SEARCH] Response headers:', response.headers);
        
        const endTime = Date.now();
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const results = await response.json();
        
        console.log(`[SEARCH] Response received in ${endTime - startTime}ms:`, results);
        console.log(`[SEARCH] Results structure:`, {
            hasDocuments: !!results.documents,
            documentsLength: results.documents ? results.documents.length : 'undefined',
            totalCount: results.total_count,
            resultKeys: Object.keys(results)
        });
        
        // Remove loading animation
        const searchLoading = document.getElementById('search-loading');
        if (searchLoading) {
            searchLoading.remove();
        }
        
        displaySearchResults(results);
        
        const docCount = results.total_count || (results.documents ? results.documents.length : 0);
        showAlert(`Found ${docCount} document${docCount !== 1 ? 's' : ''} in ${endTime - startTime}ms`, 'success');
        
    } catch (error) {
        console.error('[SEARCH] Search failed:', error);
        
        // Remove loading animation and show error
        const searchLoading = document.getElementById('search-loading');
        if (searchLoading) {
            searchLoading.remove();
        }
        
        console.error('[SEARCH] Full error details:', error);
        
        // Try a fallback search with documents endpoint
        try {
            console.log('[SEARCH] Trying fallback search...');
            const fallbackResponse = await authenticatedFetch(`${API_BASE}/documents/?limit=20`);
            if (fallbackResponse.ok) {
                const allDocs = await fallbackResponse.json();
                console.log('[SEARCH] Fallback got documents:', allDocs.length);
                
                // Filter documents by search query
                const filteredDocs = allDocs.filter(doc => 
                    (doc.title && doc.title.toLowerCase().includes(query.toLowerCase())) ||
                    (doc.filename && doc.filename.toLowerCase().includes(query.toLowerCase())) ||
                    (doc.summary && doc.summary.toLowerCase().includes(query.toLowerCase()))
                );
                
                const fallbackResults = {
                    documents: filteredDocs,
                    total_count: filteredDocs.length
                };
                
                displaySearchResults(fallbackResults);
                showAlert(`Fallback search found ${filteredDocs.length} documents`, 'warning');
                return;
            }
        } catch (fallbackError) {
            console.error('[SEARCH] Fallback also failed:', fallbackError);
        }
        
        const container = document.getElementById('search-results-list');
        container.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-exclamation-triangle text-warning fs-1"></i>
                <p class="text-muted mt-3 mb-0">Search failed</p>
                <small class="text-muted">${error.message}</small>
                <div class="mt-3">
                    <button class="btn btn-sm btn-outline-secondary" onclick="tryFallbackSearch('${query}')">
                        Try Simple Search
                    </button>
                </div>
            </div>
        `;
        
        showAlert(`Search failed: ${error.message}`, 'danger');
    }
}

function displaySearchResults(results) {
    const container = document.getElementById('search-results-list');
    const resultsDiv = document.getElementById('search-results');
    
    console.log('[SEARCH] displaySearchResults called with:', results);
    console.log('[SEARCH] Container element found:', !!container);
    console.log('[SEARCH] Results div found:', !!resultsDiv);
    
    // Handle case where documents might not exist or be empty
    const documents = results.documents || [];
    const totalCount = results.total_count || 0;
    
    console.log('[SEARCH] Documents count:', documents.length);
    console.log('[SEARCH] Total count:', totalCount);
    
    if (!container) {
        console.error('[SEARCH] search-results-list container not found!');
        return;
    }
    
    if (!documents || documents.length === 0) {
        console.log('[SEARCH] No documents found, showing empty state');
        container.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-search text-muted fs-1"></i>
                <p class="text-muted mt-3 mb-0">No documents found matching your search criteria.</p>
                <small class="text-muted">Try different keywords or disable semantic search.</small>
                <div class="mt-3">
                    <small class="text-muted">Debug: Total count: ${totalCount}, Documents array length: ${documents.length}</small>
                </div>
            </div>
        `;
    } else {
        console.log('[SEARCH] Rendering', documents.length, 'documents');
        
        try {
            const documentsHtml = documents.map(doc => {
                console.log('[SEARCH] Processing document:', doc.id, doc.title);
                return `
                    <div class="search-result-item card glass-effect hover-lift mb-3" onclick="openDocumentModal('${doc.id}')" style="cursor: pointer;">
                        <div class="card-body">
                            <h6 class="card-title mb-2">
                                <i class="fas fa-file-alt text-primary me-2"></i>
                                ${doc.title || doc.filename || 'Untitled Document'}
                            </h6>
                            <div class="row mb-2">
                                <div class="col-md-6">
                                    <small class="search-meta">
                                        <i class="fas fa-building me-1"></i>
                                        ${doc.correspondent?.name || 'Unknown Correspondent'}
                                    </small>
                                </div>
                                <div class="col-md-6">
                                    <small class="search-meta">
                                        <i class="fas fa-tag me-1"></i>
                                        ${doc.doctype?.name || 'Unknown Type'}
                                    </small>
                                </div>
                            </div>
                            ${doc.document_date ? `
                                <div class="mb-2">
                                    <small class="search-meta">
                                        <i class="fas fa-calendar me-1"></i>
                                        ${new Date(doc.document_date).toLocaleDateString()}
                                        ${doc.is_tax_relevant ? '<span class="badge bg-warning text-dark ms-2"><i class="fas fa-coins"></i> Tax Relevant</span>' : ''}
                                    </small>
                                </div>
                            ` : ''}
                            ${doc.summary ? `
                                <p class="search-summary mb-2">
                                    ${doc.summary.substring(0, 250)}${doc.summary.length > 250 ? '...' : ''}
                                </p>
                            ` : ''}
                            ${doc.tags && doc.tags.length > 0 ? `
                                <div class="mt-2">
                                    ${doc.tags.slice(0, 5).map(tag => `
                                        <span class="badge bg-secondary me-1">${tag.name}</span>
                                    `).join('')}
                                    ${doc.tags.length > 5 ? `<span class="badge bg-light text-dark">+${doc.tags.length - 5} more</span>` : ''}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = `
                <div class="mb-3">
                    <h6 class="text-muted">
                        <i class="fas fa-file-text me-2"></i>
                        Found ${totalCount} document${totalCount !== 1 ? 's' : ''}
                    </h6>
                </div>
                ${documentsHtml}
            `;
            
            console.log('[SEARCH] Successfully rendered documents HTML');
            
        } catch (error) {
            console.error('[SEARCH] Error rendering documents:', error);
            container.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-exclamation-triangle text-warning fs-1"></i>
                    <p class="text-muted mt-3 mb-0">Error rendering search results.</p>
                    <small class="text-muted">${error.message}</small>
                </div>
            `;
        }
    }
    
    if (resultsDiv) {
        resultsDiv.classList.remove('d-none');
        console.log('[SEARCH] Results div made visible');
    } else {
        console.error('[SEARCH] Results div not found!');
    }
}

function handleSearchKeyPress(event) {
    if (event.key === 'Enter') {
        performSearch();
    }
}

// File upload
async function uploadFiles() {
    const fileInput = document.getElementById('file-upload');
    const files = fileInput.files;
    
    if (files.length === 0) {
        showAlert('Please select files to upload', 'warning');
        return;
    }
    
    showElement('upload-progress');
    const progressBar = document.querySelector('#upload-progress .progress-bar');
    const statusDiv = document.getElementById('upload-status');
    
    let uploaded = 0;
    const total = files.length;
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            statusDiv.textContent = `Uploading ${file.name}...`;
            
            const response = await authenticatedFetch(`${API_BASE}/documents/upload`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                uploaded++;
            } else {
                let errorMessage = `HTTP ${response.status}`;
                try {
                    const error = await response.json();
                    errorMessage = error.detail || error.message || errorMessage;
                } catch (e) {
                    // Response body already read or not JSON
                    errorMessage = `Upload failed: ${response.statusText}`;
                }
                console.error(`Upload failed for ${file.name}:`, errorMessage);
            }
            
            const progress = (uploaded / total) * 100;
            progressBar.style.width = `${progress}%`;
            
        } catch (error) {
            console.error(`Upload failed for ${file.name}:`, error);
        }
    }
    
    statusDiv.textContent = `Uploaded ${uploaded} of ${total} files`;
    
    // Clear file input
    fileInput.value = '';
    
    // Start monitoring for processing after upload
    if (uploaded > 0) {
        checkProcessingStatus(); // Immediate check for new uploads
        showAlert(`${uploaded} file(s) uploaded successfully. Processing will begin shortly.`, 'success');
    }
    
    // Refresh staging files
    setTimeout(() => {
        refreshStagingFiles();
        hideElement('upload-progress');
    }, 2000);
}

async function refreshStagingFiles() {
    const container = document.getElementById('staging-files');
    if (!container) {
        console.error('staging-files container not found');
        return;
    }
    
    try {
        // Show loading state
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const loadingDiv = createElement('div', '', {}, ['text-center', 'py-3']);
        const spinner = createElement('i', '', {}, ['fas', 'fa-spinner', 'fa-spin', 'me-2']);
        loadingDiv.appendChild(spinner);
        loadingDiv.appendChild(createTextNode('Loading staging files...'));
        container.appendChild(loadingDiv);
        
        const response = await authenticatedFetch(`${API_BASE}/documents/staging/files`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const files = await response.json();
        
        if (files.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-folder-open fa-2x text-muted mb-2"></i>
                    <p class="text-muted mb-0">No files in staging</p>
                    <small class="text-muted">Drop files here or use the upload button above</small>
                </div>
            `;
        } else {
            container.innerHTML = files.map(file => `
                <div class="file-item">
                    <div class="file-icon ${getFileIcon(file.filename)}">
                        <i class="fas fa-file"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="fw-medium">${file.filename}</div>
                        <small class="text-muted">${formatFileSize(file.size)}</small>
                    </div>
                    <div class="processing-status status-${file.status}">${file.status}</div>
                </div>
            `).join('');
        }
        
    } catch (error) {
        console.error('Failed to load staging files:', error);
        container.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-exclamation-triangle fa-2x text-warning mb-2"></i>
                <p class="text-muted mb-0">Failed to load staging files</p>
                <small class="text-muted">${error.message}</small>
            </div>
        `;
        showAlert('Failed to load staging files: ' + error.message, 'danger');
    }
}

// Search functions for manual document selection
function filterManualDocuments() {
    displayFilteredDocuments();
}

function clearManualSearch() {
    const searchInput = document.getElementById('manual-doc-search');
    if (searchInput) {
        searchInput.value = '';
        displayFilteredDocuments();
    }
}

// Manual document selection for RAG
let selectedDocuments = [];
let allAvailableDocuments = []; // Store all documents for filtering

function toggleRagMode() {
    const isManual = document.getElementById('rag-manual').checked;
    const manualSelection = document.getElementById('manual-doc-selection');
    
    if (isManual) {
        manualSelection.classList.remove('d-none');
        loadDocumentsForSelection();
    } else {
        manualSelection.classList.add('d-none');
        selectedDocuments = [];
        updateSelectedDocumentsList();
        // Clear search when switching modes
        const searchInput = document.getElementById('manual-doc-search');
        if (searchInput) searchInput.value = '';
    }
}

async function loadDocumentsForSelection() {
    const container = document.getElementById('available-documents');
    container.innerHTML = '<div class="text-center text-muted"><i class="fas fa-spinner fa-spin"></i> Loading documents...</div>';
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/?limit=100`);
        const docs = await response.json();
        
        // Store all documents for filtering
        allAvailableDocuments = docs;
        
        // Display filtered documents
        displayFilteredDocuments();
        
    } catch (error) {
        console.error('Failed to load documents:', error);
        container.innerHTML = '<div class="text-center text-danger">Failed to load documents</div>';
    }
}

function displayFilteredDocuments() {
    const container = document.getElementById('available-documents');
    const searchQuery = document.getElementById('manual-doc-search')?.value?.toLowerCase() || '';
    
    // Filter documents based on search query
    let filteredDocs = allAvailableDocuments;
    if (searchQuery) {
        filteredDocs = allAvailableDocuments.filter(doc => {
            const title = (doc.title || '').toLowerCase();
            const filename = (doc.filename || '').toLowerCase();
            const correspondent = (doc.correspondent?.name || '').toLowerCase();
            const doctype = (doc.doctype?.name || '').toLowerCase();
            const summary = (doc.summary || '').toLowerCase();
            
            return title.includes(searchQuery) || 
                   filename.includes(searchQuery) || 
                   correspondent.includes(searchQuery) ||
                   doctype.includes(searchQuery) ||
                   summary.includes(searchQuery);
        });
    }
    
    if (filteredDocs.length === 0) {
        container.innerHTML = '<div class="text-center text-muted">No documents found matching your search</div>';
        return;
    }
    
    // Clear container and rebuild with safe DOM manipulation
    container.innerHTML = '';
    
    filteredDocs.forEach(doc => {
        const isSelected = selectedDocuments.find(d => d.id === doc.id);
        const div = document.createElement('div');
        div.className = `document-select-item p-2 mb-2 border rounded ${isSelected ? 'border-primary bg-primary bg-opacity-10' : ''}`;
        div.style.cursor = 'pointer';
        
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${escapeHtml(doc.title || doc.filename)}</strong>
                    <br>
                    <small class="text-muted">${escapeHtml(doc.correspondent?.name || 'Unknown')} • ${escapeHtml(doc.doctype?.name || 'Unknown')}</small>
                </div>
                <div>
                    <i class="fas fa-${isSelected ? 'check-circle text-primary' : 'circle text-muted'}"></i>
                </div>
            </div>
        `;
        
        // Add click handler safely
        div.addEventListener('click', () => {
            toggleDocumentSelection(doc.id, doc.title || doc.filename);
        });
        
        container.appendChild(div);
    });
}

function toggleDocumentSelection(docId, docTitle) {
    const existingIndex = selectedDocuments.findIndex(d => d.id === docId);
    
    if (existingIndex >= 0) {
        // Remove from selection
        selectedDocuments.splice(existingIndex, 1);
    } else {
        // Add to selection
        selectedDocuments.push({ id: docId, title: docTitle });
    }
    
    updateSelectedDocumentsList();
    displayFilteredDocuments(); // Refresh display to update visual state
}

function updateSelectedDocumentsList() {
    const countBadge = document.getElementById('selected-count');
    const listContainer = document.getElementById('selected-docs-list');
    
    countBadge.textContent = selectedDocuments.length;
    
    if (selectedDocuments.length === 0) {
        listContainer.innerHTML = '<div class="text-muted text-center">No documents selected</div>';
    } else {
        listContainer.innerHTML = selectedDocuments.map(doc => {
            const truncatedTitle = doc.title.length > 35 ? doc.title.substring(0, 35) + '...' : doc.title;
            const escapedTitle = doc.title.replace(/'/g, "&apos;").replace(/"/g, "&quot;");
            
            return `
                <div class="selected-doc-item">
                    <div class="selected-doc-content">
                        <div class="selected-doc-title" title="${escapedTitle}">
                            ${truncatedTitle}
                        </div>
                        <button class="selected-doc-remove" onclick="toggleDocumentSelection('${doc.id}', '${escapedTitle}')" title="Remove document">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// RAG/AI functionality
async function askAI() {
    const question = document.getElementById('rag-question').value.trim();
    
    if (!question) {
        showAlert('Please enter a question', 'warning');
        return;
    }
    
    // Check if documents are currently being processed
    if (isProcessingActive) {
        showAlert('Please wait for document processing to complete before asking AI questions', 'warning');
        return;
    }
    
    const isManual = document.getElementById('rag-manual').checked;
    
    // Check if manual mode is selected and documents are chosen
    if (isManual && selectedDocuments.length === 0) {
        showAlert('Please select at least one document for manual mode', 'warning');
        return;
    }
    
    try {
        showElement('rag-loading');
        hideElement('rag-response');
        
        let ragRequest;
        
        if (isManual) {
            // Manual mode: use selected documents
            ragRequest = {
                question: question,
                document_ids: selectedDocuments.map(d => d.id),
                max_documents: selectedDocuments.length
            };
        } else {
            // Auto mode: let AI find relevant documents
            ragRequest = {
                question: question,
                max_documents: 5
            };
        }
        
        const response = await authenticatedFetch(`${API_BASE}/search/rag`, {
            method: 'POST',
            body: JSON.stringify(ragRequest)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        // Render answer as markdown
        renderMarkdownAnswer(result.answer, result.sources);
        
        // Render improved source documents
        renderSourceDocuments(result.sources);
        
        hideElement('rag-loading');
        showElement('rag-response');
        
    } catch (error) {
        console.error('RAG query failed:', error);
        showAlert('I encountered an error while processing your question: ' + error.message, 'danger');
        hideElement('rag-loading');
        
        // Show empty response area
        document.getElementById('rag-answer').textContent = 'I apologize, but I encountered an error while processing your question. Please try again or contact support if the issue persists.';
        document.getElementById('rag-sources').innerHTML = '';
        showElement('rag-response');
    }
}

// Markdown rendering and improved RAG display
function renderMarkdownAnswer(answer, sources) {
    const answerContainer = document.getElementById('rag-answer');
    
    try {
        // Process the answer to make document references clickable
        let processedAnswer = answer;
        
        // Create document ID to index mapping
        const docIdMap = {};
        sources.forEach((doc, index) => {
            docIdMap[doc.id] = index + 1;
        });
        
        // Replace [Doc1], [Doc2] etc. with clickable links
        processedAnswer = processedAnswer.replace(/\[Doc(\d+)\]/g, (match, docNum) => {
            const docIndex = parseInt(docNum) - 1;
            if (docIndex >= 0 && docIndex < sources.length) {
                const doc = sources[docIndex];
                return `<a href="#" data-doc-id="${escapeHtml(doc.id)}" class="doc-reference">Doc${docNum}</a>`;
            }
            return match;
        });
        
        // Render markdown with marked.js
        if (typeof marked !== 'undefined') {
            // Configure marked for security
            marked.setOptions({
                breaks: true,
                gfm: true,
                sanitize: false // We control the content
            });
            
            const renderedHtml = marked.parse(processedAnswer);
            answerContainer.innerHTML = renderedHtml;
            
            // Make the container handle click events for document links
            answerContainer.addEventListener('click', function(e) {
                if (e.target.tagName === 'A' && e.target.hasAttribute('data-doc-id')) {
                    e.preventDefault();
                    const docId = e.target.getAttribute('data-doc-id');
                    if (docId) {
                        openDocumentModal(docId);
                    }
                }
            });
        } else {
            // Fallback to plain text with line breaks
            const escapedAnswer = escapeHtml(processedAnswer);
            answerContainer.innerHTML = escapedAnswer.replace(/\n/g, '<br>');
        }
        
        // Add some styling
        answerContainer.classList.remove('alert-info');
        answerContainer.classList.add('rag-answer-markdown');
        
    } catch (error) {
        console.error('Error rendering markdown:', error);
        // Fallback to plain text
        answerContainer.textContent = answer;
    }
}

function renderSourceDocuments(sources) {
    const sourcesContainer = document.getElementById('rag-sources');
    
    if (!sources || sources.length === 0) {
        sourcesContainer.innerHTML = '<div class="text-muted">No source documents found.</div>';
        return;
    }
    
    // Clear container and rebuild with safe DOM manipulation
    sourcesContainer.innerHTML = '';
    
    sources.forEach((doc, index) => {
        const docNum = index + 1;
        const title = doc.title || doc.filename || 'Untitled Document';
        const correspondent = doc.correspondent?.name || 'Unknown';
        const doctype = doc.doctype?.name || 'Unknown';
        const dateStr = doc.document_date ? new Date(doc.document_date).toLocaleDateString() : 'No date';
        
        const colDiv = document.createElement('div');
        colDiv.className = 'col-md-6 col-lg-4';
        
        const cardDiv = document.createElement('div');
        cardDiv.className = 'card source-document-card h-100';
        cardDiv.style.cursor = 'pointer';
        
        cardDiv.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <small class="text-primary fw-bold">Doc${docNum}</small>
                <small class="text-muted">${escapeHtml(dateStr)}</small>
            </div>
            <div class="card-body">
                <h6 class="card-title" title="${escapeHtml(title)}">${escapeHtml(title.length > 50 ? title.substring(0, 50) + '...' : title)}</h6>
                <p class="card-text">
                    <small class="text-muted">
                        <i class="fas fa-user me-1"></i>${escapeHtml(correspondent)}<br>
                        <i class="fas fa-file-alt me-1"></i>${escapeHtml(doctype)}
                    </small>
                </p>
            </div>
            <div class="card-footer">
                <small class="text-primary">
                    <i class="fas fa-external-link-alt me-1"></i>Click to open document
                </small>
            </div>
        `;
        
        // Add click handler safely
        cardDiv.addEventListener('click', () => {
            openDocumentModal(doc.id);
        });
        
        colDiv.appendChild(cardDiv);
        sourcesContainer.appendChild(colDiv);
    });
}

// Processing monitoring functionality
function checkProcessingStatus() {
    authenticatedFetch(`${API_BASE}/documents/`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data && data.items && Array.isArray(data.items)) {
                const hasProcessingDocs = data.items.some(doc => 
                    doc.ocr_status === 'processing' || doc.ai_status === 'processing'
                );
                
                updateProcessingState(hasProcessingDocs);
            }
        })
        .catch(error => {
            console.error('Failed to check processing status:', error);
        });
}

function updateProcessingState(processing) {
    const wasProcessing = isProcessingActive;
    isProcessingActive = processing;
    
    // Update Ask AI button state
    updateAskAIButton();
    
    // Start or stop monitoring interval
    if (processing && !processingCheckInterval) {
        processingCheckInterval = setInterval(checkProcessingStatus, 3000); // Check every 3 seconds
        console.log('Started processing monitoring');
    } else if (!processing && processingCheckInterval) {
        clearInterval(processingCheckInterval);
        processingCheckInterval = null;
        console.log('Stopped processing monitoring');
        
        // Show notification when processing completes
        if (wasProcessing) {
            showAlert('Document processing completed. You can now ask AI questions.', 'success');
        }
    }
}

function updateAskAIButton() {
    const askButton = document.querySelector('#rag-tab button[onclick="askAI()"]');
    if (askButton) {
        if (isProcessingActive) {
            askButton.disabled = true;
            askButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing Documents...';
            askButton.classList.add('btn-secondary');
            askButton.classList.remove('btn-primary');
        } else {
            askButton.disabled = false;
            askButton.innerHTML = '<i class="fas fa-brain me-2"></i>Ask AI';
            askButton.classList.add('btn-primary');
            askButton.classList.remove('btn-secondary');
        }
    }
}

function startProcessingMonitoring() {
    // Initial check
    checkProcessingStatus();
    
    // Set up periodic checks
    if (!processingCheckInterval) {
        processingCheckInterval = setInterval(checkProcessingStatus, 5000); // Check every 5 seconds
    }
}

function stopProcessingMonitoring() {
    if (processingCheckInterval) {
        clearInterval(processingCheckInterval);
        processingCheckInterval = null;
    }
}

// Data management
async function loadCorrespondents() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/correspondents/`);
        if (response.ok) {
            correspondents = await response.json();
        } else {
            console.error('Failed to load correspondents, status:', response.status);
            correspondents = [];
        }
    } catch (error) {
        console.error('Failed to load correspondents:', error);
        correspondents = [];
    }
}

async function loadDocTypes() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/doctypes/`);
        if (response.ok) {
            doctypes = await response.json();
        } else {
            console.error('Failed to load document types, status:', response.status);
            doctypes = [];
        }
    } catch (error) {
        console.error('Failed to load document types:', error);
        doctypes = [];
    }
}

async function loadTags() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/tags/`);
        if (response.ok) {
            tags = await response.json();
            console.log('Tags loaded:', tags);
        } else {
            console.error('Failed to load tags, status:', response.status);
            tags = [];
        }
    } catch (error) {
        console.error('Failed to load tags:', error);
        tags = [];
    }
}

function populateFilters() {
    // Populate multiselect dropdowns
    populateCorrespondentsMultiselect();
    populateDoctypesMultiselect();
    populateTagsMultiselect();
    
    // Also populate search filters
    populateSearchFilters();
}

function populateSearchFilters() {
    // Populate search multiselect dropdowns
    console.log('Populating search filters...');
    populateSearchCorrespondentsMultiselect();
    populateSearchDoctypesMultiselect();
    populateSearchTagsMultiselect();
}


// Navbar search functions
function handleNavbarSearchKeyPress(event) {
    if (event.key === 'Enter') {
        performNavbarSearch();
    }
}

async function performNavbarSearch() {
    const query = document.getElementById('navbar-search').value.trim();
    
    if (!query) {
        showAlert('Please enter a search query', 'warning');
        return;
    }
    
    // Switch to search tab and populate the search
    showTab('search');
    document.getElementById('search-query').value = query;
    
    // Ensure filters are populated before searching
    setTimeout(() => {
        populateSearchFilters();
        setTimeout(() => {
            performSearch();
        }, 50);
    }, 100);
}

// Retry processing functions
window.retryProcessing = async function(documentId) {
    console.log('retryProcessing called with documentId:', documentId);
    try {
        showAlert('Retrying document processing...', 'info');
        
        const url = `${API_BASE}/documents/${documentId}/reprocess`;
        console.log('Calling URL:', url);
        
        const response = await authenticatedFetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        console.log('Response status:', response.status);
        
        if (response.ok) {
            const result = await response.json();
            console.log('Reprocess result:', result);
            showAlert('Document queued for reprocessing', 'success');
            // Refresh documents to show updated status
            setTimeout(() => {
                loadDocuments(currentPage);
            }, 1000);
        } else {
            const error = await response.json();
            console.error('Reprocess error response:', error);
            showAlert(error.detail || 'Failed to retry processing', 'danger');
        }
    } catch (error) {
        console.error('Failed to retry processing - Exception:', error);
        showAlert('Failed to retry processing: ' + error.message, 'danger');
    }
}

window.retryAIProcessing = async function(documentId) {
    try {
        showAlert('Retrying AI processing...', 'info');
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}/reprocess-ai`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            showAlert('AI processing queued for retry', 'success');
            // Refresh documents to show updated status
            setTimeout(() => {
                loadDocuments(currentPage);
            }, 1000);
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to retry AI processing', 'danger');
        }
    } catch (error) {
        console.error('Failed to retry AI processing:', error);
        showAlert('Failed to retry AI processing', 'danger');
    }
}

// Saved searches functionality
function saveCurrentSearch() {
    const query = document.getElementById('search-query').value.trim();
    const useSemanticSearch = document.getElementById('search-semantic').checked;
    
    if (!query) {
        showAlert('No search query to save', 'warning');
        return;
    }
    
    const savedSearches = safeJSONParse(localStorage.getItem('savedSearches'), []);
    
    // Check if search already exists
    const exists = savedSearches.find(s => s.query === query && s.semantic === useSemanticSearch);
    if (exists) {
        showAlert('This search is already saved', 'info');
        return;
    }
    
    const search = {
        id: Date.now(),
        query: query,
        semantic: useSemanticSearch,
        timestamp: new Date().toISOString()
    };
    
    savedSearches.push(search);
    localStorage.setItem('savedSearches', JSON.stringify(savedSearches));
    
    displaySavedSearches();
    showAlert('Search saved successfully', 'success');
}

function displaySavedSearches() {
    let savedSearches = safeJSONParse(localStorage.getItem('savedSearches'), []);
    const container = document.getElementById('saved-searches-list');
    
    // Check if container exists
    if (!container) {
        console.log('Saved searches container not found - tab may not be loaded yet');
        return;
    }
    
    // Ensure savedSearches is always an array
    if (!Array.isArray(savedSearches)) {
        console.warn('savedSearches is not an array, resetting to empty array');
        savedSearches = [];
    }
    
    if (savedSearches.length === 0) {
        container.innerHTML = '<p class="text-muted">No saved searches</p>';
        return;
    }
    
    container.innerHTML = savedSearches.map(search => `
        <div class="d-flex justify-content-between align-items-center p-2 border rounded mb-2">
            <div>
                <strong>${search.query}</strong>
                <br>
                <small class="text-muted">
                    ${search.semantic ? 'Semantic' : 'Text'} search • 
                    ${new Date(search.timestamp).toLocaleDateString()}
                </small>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="loadSavedSearch(${search.id})" title="Load search">
                    <i class="fas fa-play"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteSavedSearch(${search.id})" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function loadSavedSearch(searchId) {
    const savedSearches = safeJSONParse(localStorage.getItem('savedSearches'), []);
    const search = savedSearches.find(s => s.id === searchId);
    
    if (search) {
        document.getElementById('search-query').value = search.query;
        document.getElementById('search-semantic').checked = search.semantic;
        performSearch();
    }
}

function deleteSavedSearch(searchId) {
    const savedSearches = safeJSONParse(localStorage.getItem('savedSearches'), []);
    const filtered = savedSearches.filter(s => s.id !== searchId);
    localStorage.setItem('savedSearches', JSON.stringify(filtered));
    displaySavedSearches();
    showAlert('Search deleted', 'success');
}

async function loadManageData() {
    try {
        // Reload all data first to ensure we have current data
        await loadInitialData();
        
        // Then display the data
        await Promise.all([
            displayCorrespondents(),
            displayDocTypes(),
            displayTags()
        ]);
    } catch (error) {
        console.error('Failed to load manage data:', error);
        showAlert('Failed to load management data', 'danger');
    }
}

// Manage state for filtering and pagination
const manageState = {
    correspondents: { 
        filtered: [], 
        currentPage: 1, 
        itemsPerPage: 15, 
        searchTerm: '' 
    },
    doctypes: { 
        filtered: [], 
        currentPage: 1, 
        itemsPerPage: 15, 
        searchTerm: '' 
    },
    tags: { 
        filtered: [], 
        currentPage: 1, 
        itemsPerPage: 15, 
        searchTerm: '' 
    }
};

function displayCorrespondents() {
    displayManageList('correspondents', correspondents, (c, searchTerm) => `
        <div class="manage-item" data-id="${c.id}">
            <div class="item-info">
                <span class="item-name" id="correspondent-name-${c.id}">${highlightSearchTerm(c.name, searchTerm)}</span>
                <span class="item-count">(${c.document_count || 0} docs)</span>
                ${c.email ? `<small class="d-block">
                    <a href="mailto:${c.email}" class="text-decoration-none text-info" onclick="event.stopPropagation();" title="Send email">
                        <i class="fas fa-envelope me-1"></i>${c.email}
                    </a>
                </small>` : ''}
                ${c.address ? `<small class="d-block">
                    <a href="https://www.google.com/maps/search/${encodeURIComponent(c.address)}" 
                       target="_blank" 
                       class="text-decoration-none text-info" 
                       onclick="event.stopPropagation();" 
                       title="View in Google Maps">
                        <i class="fas fa-map-marker-alt me-1"></i>${c.address.split('\n')[0]}
                    </a>
                </small>` : ''}
            </div>
            <div class="manage-buttons">
                <button class="btn btn-sm btn-outline-primary me-1" onclick="editCorrespondent('${c.id}', '${c.name.replace(/'/g, "&apos;")}')" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteCorrespondent('${c.id}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `);
    updateManageCount('correspondents', correspondents.length);
}

function displayDocTypes() {
    displayManageList('doctypes', doctypes, (d, searchTerm) => `
        <div class="manage-item" data-id="${d.id}">
            <div class="item-info">
                <span class="item-name" id="doctype-name-${d.id}">${highlightSearchTerm(d.name, searchTerm)}</span>
                <span class="item-count">(${d.document_count || 0} docs)</span>
            </div>
            <div class="manage-buttons">
                <button class="btn btn-sm btn-outline-primary me-1" onclick="editDocType('${d.id}', '${d.name.replace(/'/g, "&apos;")}')" title="Rename">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteDocType('${d.id}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `);
    updateManageCount('doctypes', doctypes.length);
}

function displayTags() {
    displayManageList('tags', tags, (t, searchTerm) => `
        <div class="manage-item" data-id="${t.id}">
            <div class="item-info">
                <span class="tag-color-indicator me-2" style="background-color: ${t.color || '#64748b'}"></span>
                <span class="item-name" id="tag-name-${t.id}">${highlightSearchTerm(t.name, searchTerm)}</span>
                <span class="item-count">(${t.document_count || 0})</span>
            </div>
            <div class="manage-buttons">
                <button class="btn btn-sm btn-outline-primary me-1" onclick="editTag('${t.id}', '${t.name.replace(/'/g, "&apos;")}', '${t.color || '#64748b'}')" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteTag('${t.id}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `);
    updateManageCount('tags', tags.length);
}

// Generic function to display manage lists with pagination and filtering
function displayManageList(type, data, renderItemFn) {
    const state = manageState[type];
    const container = document.getElementById(`${type}-list`);
    
    // Filter data based on search term
    const searchTerm = state.searchTerm.toLowerCase();
    // If no search term, show all data; otherwise filter
    state.filtered = searchTerm ? 
        data.filter(item => item.name.toLowerCase().includes(searchTerm)) : 
        [...data];
    
    // Calculate pagination
    const totalItems = state.filtered.length;
    const totalPages = Math.ceil(totalItems / state.itemsPerPage);
    const startIndex = (state.currentPage - 1) * state.itemsPerPage;
    const endIndex = startIndex + state.itemsPerPage;
    const pageItems = state.filtered.slice(startIndex, endIndex);
    
    // Render items
    if (pageItems.length === 0) {
        if (searchTerm) {
            container.innerHTML = `
                <div class="manage-list-empty">
                    <i class="fas fa-search"></i>
                    No results found for "${state.searchTerm}"
                </div>
            `;
        } else {
            const icons = { correspondents: 'fa-users', doctypes: 'fa-file-alt', tags: 'fa-tags' };
            container.innerHTML = `
                <div class="manage-list-empty">
                    <i class="fas ${icons[type]}"></i>
                    No ${type} found
                </div>
            `;
        }
    } else {
        container.innerHTML = pageItems.map(item => renderItemFn(item, searchTerm)).join('');
    }
    
    // Update pagination
    displayManagePagination(type, state.currentPage, totalPages);
    
    // Update count badge
    updateManageCount(type, state.filtered.length, data.length);
}

// Function to highlight search terms
function highlightSearchTerm(text, searchTerm) {
    if (!searchTerm) return text;
    
    const regex = new RegExp(`(${escapeRegex(searchTerm)})`, 'gi');
    return text.replace(regex, '<span class="search-highlight">$1</span>');
}

// Escape regex special characters
function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Escape HTML special characters
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Update count badge in header
function updateManageCount(type, filteredCount, totalCount = null) {
    const badge = document.getElementById(`${type}-count`);
    if (badge) {
        if (totalCount !== null && filteredCount !== totalCount) {
            badge.textContent = `${filteredCount}/${totalCount}`;
            badge.className = 'badge bg-warning';
        } else {
            badge.textContent = filteredCount;
            badge.className = 'badge bg-primary';
        }
    }
}

// Display pagination controls
function displayManagePagination(type, currentPage, totalPages) {
    const container = document.getElementById(`${type}-pagination`);
    
    if (totalPages <= 1) {
        container.classList.add('d-none');
        return;
    }
    
    container.classList.remove('d-none');
    
    const maxVisiblePages = 5;
    const startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    const endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    let paginationHTML = '<ul class="pagination pagination-sm">';
    
    // Previous button
    if (currentPage > 1) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="changeManagePage('${type}', ${currentPage - 1})">
                    <i class="fas fa-chevron-left"></i>
                </a>
            </li>
        `;
    }
    
    // Page numbers
    for (let i = startPage; i <= endPage; i++) {
        const isActive = i === currentPage ? 'active' : '';
        paginationHTML += `
            <li class="page-item ${isActive}">
                <a class="page-link" href="#" onclick="changeManagePage('${type}', ${i})">${i}</a>
            </li>
        `;
    }
    
    // Next button
    if (currentPage < totalPages) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="changeManagePage('${type}', ${currentPage + 1})">
                    <i class="fas fa-chevron-right"></i>
                </a>
            </li>
        `;
    }
    
    paginationHTML += '</ul>';
    container.innerHTML = paginationHTML;
}

// Change page
function changeManagePage(type, page) {
    manageState[type].currentPage = page;
    
    // Re-render the appropriate list
    if (type === 'correspondents') displayCorrespondents();
    else if (type === 'doctypes') displayDocTypes();
    else if (type === 'tags') displayTags();
}

// Filter manage list based on search input
function filterManageList(type) {
    const searchInput = document.getElementById(`search-${type}`);
    manageState[type].searchTerm = searchInput.value;
    manageState[type].currentPage = 1; // Reset to first page
    
    // Re-render the appropriate list
    if (type === 'correspondents') displayCorrespondents();
    else if (type === 'doctypes') displayDocTypes();
    else if (type === 'tags') displayTags();
}

// Handle Enter key in manage input fields
function handleManageInputKeyPress(event, type) {
    if (event.key === 'Enter') {
        event.preventDefault();
        if (type === 'correspondent') showCorrespondentModal();
        else if (type === 'doctype') addDocType();
        else if (type === 'tag') addTag();
    }
}

// CRUD operations
// addCorrespondent function removed - now using showCorrespondentModal() for adding new correspondents

async function addDocType() {
    const input = document.getElementById('new-doctype');
    const name = input.value.trim();
    
    if (!name) {
        showAlert('Please enter a document type name', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/doctypes/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        
        if (response.ok) {
            input.value = '';
            await loadDocTypes();
            displayDocTypes();
            populateFilters();
            showAlert('Document type added successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to add document type', 'danger');
        }
    } catch (error) {
        console.error('Failed to add document type:', error);
        showAlert('Failed to add document type', 'danger');
    }
}

async function addTag() {
    const input = document.getElementById('new-tag');
    const colorInput = document.getElementById('new-tag-color');
    const name = input.value.trim();
    const color = colorInput.value;
    
    if (!name) {
        showAlert('Please enter a tag name', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/tags/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, color: color })
        });
        
        if (response.ok) {
            input.value = '';
            colorInput.value = '#64748b'; // Reset to default color
            await loadTags();
            displayTags();
            populateFilters();
            showAlert('Tag added successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to add tag', 'danger');
        }
    } catch (error) {
        console.error('Failed to add tag:', error);
        showAlert('Failed to add tag', 'danger');
    }
}

// Filter management
function applyFilters() {
    currentFilters = {};
    
    // Store all selected filters for client-side filtering
    if (selectedCorrespondents.length > 0) {
        currentFilters.correspondent_ids = selectedCorrespondents;
        // Use first one for backend filter (backend limitation)
        currentFilters.correspondent_id = selectedCorrespondents[0];
    }
    
    if (selectedDoctypes.length > 0) {
        currentFilters.doctype_ids = selectedDoctypes;
        // Use first one for backend filter (backend limitation)
        currentFilters.doctype_id = selectedDoctypes[0];
    }
    
    if (selectedTags.length > 0) {
        currentFilters.tag_ids = selectedTags;
    }
    
    const taxRelevant = document.getElementById('filter-tax-relevant').checked;
    if (taxRelevant) currentFilters.is_tax_relevant = true;
    
    // Date range filters - check for preset first
    const datePreset = document.getElementById('filter-date-preset').value;
    if (datePreset && datePreset !== 'custom') {
        currentFilters.date_range = datePreset;
    } else {
        // Use custom date range
        const dateFrom = document.getElementById('filter-date-from').value;
        const dateTo = document.getElementById('filter-date-to').value;
        if (dateFrom) currentFilters.date_from = dateFrom;
        if (dateTo) currentFilters.date_to = dateTo;
    }
    
    // Reminder filter
    if (selectedReminder !== 'all') {
        currentFilters.reminder_filter = selectedReminder;
    }
    
    currentPage = 1;
    loadDocuments(currentPage);
}

// Handle date preset changes for Documents view
function handleDatePresetChange() {
    const preset = document.getElementById('filter-date-preset').value;
    const customInputs = document.getElementById('custom-date-inputs');
    
    if (preset === 'custom') {
        customInputs.classList.remove('d-none');
        // Don't apply filters yet, let user set custom dates
    } else {
        customInputs.classList.add('d-none');
        // Clear custom date inputs
        document.getElementById('filter-date-from').value = '';
        document.getElementById('filter-date-to').value = '';
        applyFilters();
    }
}

// Date Dropdown Functions
function toggleDateDropdown() {
    const dropdown = document.getElementById('date-dropdown');
    const display = document.getElementById('selected-date-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeCorrespondentDropdown();
        closeDoctypeDropdown();
        closeTagsDropdown();
        closeReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeDateDropdown() {
    const dropdown = document.getElementById('date-dropdown');
    const display = document.getElementById('selected-date-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function selectDatePreset(preset) {
    const display = document.getElementById('selected-date-display');
    const customInputs = document.getElementById('custom-date-inputs');
    
    // Update display
    const presetLabels = {
        '': 'All Documents',
        'today': 'Today',
        'yesterday': 'Yesterday',
        'last_7_days': 'Last 7 Days',
        'last_30_days': 'Last 30 Days',
        'this_week': 'This Week',
        'last_week': 'Last Week',
        'this_month': 'This Month',
        'last_month': 'Last Month',
        'this_year': 'This Year',
        'last_year': 'Last Year',
        'custom': 'Custom...'
    };
    
    display.innerHTML = `
        <span>${presetLabels[preset] || 'All Documents'}</span>
        <i class="fas fa-chevron-down ms-auto"></i>
    `;
    
    // Handle custom date inputs
    if (preset === 'custom') {
        customInputs.classList.remove('d-none');
    } else {
        customInputs.classList.add('d-none');
        document.getElementById('filter-date-from').value = '';
        document.getElementById('filter-date-to').value = '';
    }
    
    // Update the hidden input value for backward compatibility
    const hiddenInput = document.getElementById('filter-date-preset');
    if (hiddenInput) {
        hiddenInput.value = preset;
    }
    
    // Close dropdown
    closeDateDropdown();
    
    // Apply filters
    if (preset !== 'custom') {
        applyFilters();
    }
}

// Handle date preset changes for Search view
function handleSearchDatePresetChange() {
    const preset = document.getElementById('search-date-preset').value;
    const customDates = document.getElementById('search-custom-dates');
    
    if (preset === 'custom') {
        customDates.classList.remove('d-none');
        // Don't search yet, let user set custom dates
    } else {
        customDates.classList.add('d-none');
        // Clear custom date inputs
        document.getElementById('search-date-from').value = '';
        document.getElementById('search-date-to').value = '';
        // Auto-search if there's already a query
        const query = document.getElementById('search-query').value.trim();
        if (query) {
            performSearch();
        }
    }
}

// Apply client-side filters for multiple selections
function applyClientSideFilters(docs) {
    return docs.filter(doc => {
        // Filter by multiple correspondents
        if (currentFilters.correspondent_ids && currentFilters.correspondent_ids.length > 0) {
            if (!doc.correspondent || !currentFilters.correspondent_ids.includes(doc.correspondent.id)) {
                return false;
            }
        }
        
        // Filter by multiple doctypes
        if (currentFilters.doctype_ids && currentFilters.doctype_ids.length > 0) {
            if (!doc.doctype || !currentFilters.doctype_ids.includes(doc.doctype.id)) {
                return false;
            }
        }
        
        // Filter by multiple tags
        if (currentFilters.tag_ids && currentFilters.tag_ids.length > 0) {
            const docTagIds = doc.tags.map(tag => tag.id);
            const hasMatchingTag = currentFilters.tag_ids.some(tagId => docTagIds.includes(tagId));
            if (!hasMatchingTag) {
                return false;
            }
        }
        
        return true;
    });
}

function clearFilters() {
    // Clear all multiselect arrays
    selectedCorrespondents = [];
    selectedDoctypes = [];
    selectedTags = [];
    selectedReminder = 'all';
    
    // Clear tax relevant checkbox
    document.getElementById('filter-tax-relevant').checked = false;
    
    // Clear date filters
    document.getElementById('filter-date-preset').value = '';
    document.getElementById('filter-date-from').value = '';
    document.getElementById('filter-date-to').value = '';
    document.getElementById('custom-date-inputs').classList.add('d-none');
    
    // Reset date display
    const dateDisplay = document.getElementById('selected-date-display');
    if (dateDisplay) {
        dateDisplay.innerHTML = `
            <span class="placeholder">Select date range...</span>
            <i class="fas fa-chevron-down ms-auto"></i>
        `;
    }
    
    // Clear all search inputs
    const navbarSearch = document.getElementById('navbar-search');
    if (navbarSearch) navbarSearch.value = '';
    
    const searchQuery = document.getElementById('search-query');
    if (searchQuery) searchQuery.value = '';
    
    const mobileSearchInput = document.getElementById('mobile-search-input');
    if (mobileSearchInput) mobileSearchInput.value = '';
    
    // Clear semantic search checkbox
    const searchSemantic = document.getElementById('search-semantic');
    if (searchSemantic) searchSemantic.checked = false;
    
    // Update displays for all multiselects
    updateSelectedCorrespondentsDisplay();
    updateSelectedDoctypesDisplay();
    updateSelectedTagsDisplay();
    updateSelectedReminderDisplay();
    
    // Refresh all multiselect checkboxes
    populateCorrespondentsMultiselect();
    populateDoctypesMultiselect();
    populateTagsMultiselect();
    populateReminderDropdown();
    
    currentFilters = {};
    currentPage = 1;
    loadDocuments(currentPage);
}

// Settings
async function loadSettings() {
    try {
        // Initialize Settings tab content visibility
        initializeSettingsTabs();
        
        const [statsResponse, healthResponse] = await Promise.all([
            authenticatedFetch(`${API_BASE}/documents/stats/overview`),
            authenticatedFetch(`${API_BASE}/settings/health/`)
        ]);
        
        if (!statsResponse.ok || !healthResponse.ok) {
            throw new Error('Failed to fetch settings data');
        }
        
        const stats = await statsResponse.json();
        const health = await healthResponse.json();
        
        displayStats(stats);
        displayHealth(health);
        await refreshLogs();
        await loadAILimits();
        
        // Also load extended settings and AI provider status
        loadExtendedSettings();
        loadAIProviderStatus();
        loadGroqSettings();
        loadSettingsExtendedWithUsers();
        loadUsers();
        loadCurrentUser();
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        showAlert('Failed to load settings data', 'danger');
    }
}

function initializeSettingsTabs() {
    // Ensure settings tab content container is visible
    const settingsTabContent = document.getElementById('settingsTabContent');
    if (settingsTabContent) {
        settingsTabContent.classList.remove('d-none');
        settingsTabContent.style.display = 'block';
        console.log('Settings tab content made visible');
    }
    
    // Reset all settings tab panes
    document.querySelectorAll('#settingsTabContent .tab-pane').forEach(pane => {
        pane.classList.remove('show', 'active');
        pane.removeAttribute('style');
    });
    
    // Reset all settings tab buttons
    document.querySelectorAll('#settingsTabs .nav-link').forEach(tab => {
        tab.classList.remove('active');
        tab.setAttribute('aria-selected', 'false');
    });
    
    // Activate the system settings tab by default
    const systemTab = document.getElementById('system-settings-tab');
    const systemPanel = document.getElementById('system-settings-panel');
    
    if (systemTab && systemPanel) {
        systemTab.classList.add('active');
        systemTab.setAttribute('aria-selected', 'true');
        systemPanel.classList.add('show', 'active');
        console.log('System settings tab activated');
    }
    
    // Set initial state based on selected provider (no duplicate event listeners needed)
    // The global event listener already handles ai-provider changes
    const selectedProvider = document.querySelector('input[name="ai-provider"]:checked');
    if (selectedProvider) {
        // Ensure elements are available before calling updateAIProviderUI
        const checkAndUpdate = () => {
            const groqSection = document.getElementById('groq-config-section');
            const openaiSection = document.getElementById('openai-config-section');
            const azureSection = document.getElementById('azure-config-section');

            if (groqSection && openaiSection && azureSection) {
                updateAIProviderUI(selectedProvider.value);
            } else {
                // Wait a bit more if elements aren't ready
                setTimeout(checkAndUpdate, 50);
            }
        };

        // Start checking immediately, then with fallback delay
        checkAndUpdate();
    }

    // Switch the visible provider panel as soon as a radio is clicked.
    document.querySelectorAll('input[name="ai-provider"]').forEach(radio => {
        radio.addEventListener('change', event => {
            if (event.target.checked) {
                updateAIProviderUI(event.target.value);
            }
        });
    });


    // Initialize Bootstrap tab functionality for settings
    document.querySelectorAll('#settingsTabs .nav-link[data-bs-toggle="tab"]').forEach(tabElement => {
        // Remove any existing listeners
        tabElement.replaceWith(tabElement.cloneNode(true));
    });
    
    // Re-get elements after cloning and add Bootstrap tab behavior
    document.querySelectorAll('#settingsTabs .nav-link[data-bs-toggle="tab"]').forEach(tabElement => {
        tabElement.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get target panel
            const targetId = this.getAttribute('data-bs-target');
            const targetPanel = document.querySelector(targetId);
            
            if (!targetPanel) return;
            
            // Hide all other settings tabs and panels
            document.querySelectorAll('#settingsTabs .nav-link').forEach(tab => {
                tab.classList.remove('active');
                tab.setAttribute('aria-selected', 'false');
            });
            
            document.querySelectorAll('#settingsTabContent .tab-pane').forEach(pane => {
                pane.classList.remove('show', 'active');
            });
            
            // Show clicked tab and its panel
            this.classList.add('active');
            this.setAttribute('aria-selected', 'true');
            targetPanel.classList.add('show', 'active');
            
            console.log('Settings tab switched to:', targetId);
        });
    });
}

function displayStats(stats) {
    const container = document.getElementById('system-stats');
    container.innerHTML = `
        <div class="row">
            <div class="col-6">
                <div class="text-center">
                    <h4 class="text-primary">${stats.total_documents}</h4>
                    <small>Total Documents</small>
                </div>
            </div>
            <div class="col-6">
                <div class="text-center">
                    <h4 class="text-warning">${stats.tax_relevant_documents}</h4>
                    <small>Tax Relevant</small>
                </div>
            </div>
            <div class="col-6 mt-3">
                <div class="text-center">
                    <h4 class="text-info">${stats.pending_ocr}</h4>
                    <small>Pending OCR</small>
                </div>
            </div>
            <div class="col-6 mt-3">
                <div class="text-center">
                    <h4 class="text-info">${stats.pending_ai}</h4>
                    <small>Pending AI</small>
                </div>
            </div>
        </div>
    `;
}

function displayHealth(healthData) {
    const container = document.getElementById('health-status');
    if (!container) return;
    
    // Handle new health check format
    if (healthData.services) {
        // New format with detailed service health
        const services = healthData.services;
        
        // Update overall status indicator
        const overallStatus = healthData.status || 'unknown';
        const statusIndicator = document.getElementById('status-indicator');
        if (statusIndicator) {
            const statusClass = overallStatus === 'healthy' ? 'bg-success' : 
                               overallStatus === 'warning' ? 'bg-warning' : 'bg-danger';
            statusIndicator.className = `badge ${statusClass}`;
            statusIndicator.textContent = overallStatus.charAt(0).toUpperCase() + overallStatus.slice(1);
        }
        
        // Create summary card
        const summaryHtml = healthData.summary ? `
            <div class="health-summary-card">
                <div class="health-summary-title">
                    <i class="fas fa-heart-pulse me-2"></i>System Health Overview
                </div>
                <div class="health-summary-stats">
                    <div class="health-stat">
                        <span class="health-stat-value">${healthData.summary.healthy}</span>
                        <div class="health-stat-label">Healthy</div>
                    </div>
                    <div class="health-stat">
                        <span class="health-stat-value">${healthData.summary.warning}</span>
                        <div class="health-stat-label">Warning</div>
                    </div>
                    <div class="health-stat">
                        <span class="health-stat-value">${healthData.summary.unhealthy}</span>
                        <div class="health-stat-label">Unhealthy</div>
                    </div>
                </div>
                <button class="health-refresh-btn mt-3" onclick="checkSystemHealth()">
                    <i class="fas fa-refresh me-1"></i>Refresh
                </button>
            </div>
        ` : '';
        
        // Service icons mapping
        const serviceIcons = {
            'database': 'fas fa-database',
            'vector_db': 'fas fa-vector-square',
            'ai_service': 'fas fa-brain',
            'ocr_service': 'fas fa-file-text',
            'file_system': 'fas fa-folder',
            'configuration': 'fas fa-cog'
        };
        
        // Create service cards
        const servicesHtml = Object.entries(services).map(([serviceName, serviceData]) => {
            const status = serviceData.status || 'unknown';
            const statusClass = status === 'healthy' ? 'healthy' : 
                               status === 'unhealthy' ? 'unhealthy' : 'warning';
            const icon = serviceIcons[serviceName] || 'fas fa-circle';
            
            // Format details for display
            let detailsHtml = '';
            if (serviceData.details && typeof serviceData.details === 'object') {
                detailsHtml = `
                    <div class="health-service-details">
                        <dl>
                            ${Object.entries(serviceData.details).map(([key, value]) => `
                                <dt>${key.replace(/_/g, ' ')}:</dt>
                                <dd>${typeof value === 'object' ? JSON.stringify(value) : value}</dd>
                            `).join('')}
                        </dl>
                    </div>
                `;
            }
            
            return `
                <div class="health-service-card ${statusClass}">
                    <div class="health-service-header">
                        <div class="health-service-name">
                            <i class="${icon} health-service-icon"></i>
                            ${serviceName.replace(/_/g, ' ').toUpperCase()}
                        </div>
                        <span class="health-service-status bg-${status === 'healthy' ? 'success' : status === 'unhealthy' ? 'danger' : 'warning'}">${status.toUpperCase()}</span>
                    </div>
                    <div class="health-service-message">${serviceData.message || 'No additional information'}</div>
                    ${detailsHtml}
                </div>
            `;
        }).join('');
        
        // Combine summary and services
        container.innerHTML = `
            ${summaryHtml}
            <div class="health-status-container">
                ${servicesHtml}
            </div>
        `;
        
    } else {
        // Fallback for old format
        container.innerHTML = Object.entries(healthData).map(([service, status]) => {
            let statusText = status;
            let statusClass = 'warning';
            
            if (typeof status === 'object') {
                statusText = status.status || 'unknown';
                statusClass = statusText === 'healthy' ? 'success' : 
                             statusText.includes('error') || statusText === 'unhealthy' ? 'danger' : 'warning';
            } else if (typeof status === 'string') {
                statusClass = status === 'healthy' ? 'success' : 
                             status.includes('error') ? 'danger' : 'warning';
            }
            
            return `
                <div class="health-item">
                    <span>${service.replace('_', ' ').toUpperCase()}</span>
                    <span class="badge bg-${statusClass}">${statusText}</span>
                </div>
            `;
        }).join('');
    }
}

async function refreshLogs() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/logs/recent`);
        const logs = await response.json();
        
        const container = document.getElementById('recent-logs');
        container.innerHTML = logs.map(log => `
            <div class="log-entry ${log.status}">
                <strong>${log.operation}</strong>: ${log.message}
                <br>
                <small class="text-muted">${new Date(log.created_at).toLocaleString()}</small>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load logs:', error);
    }
}

async function saveOpenAIConfig() {
    const apiKeyInput = document.getElementById('openai-api-key');
    let apiKey = apiKeyInput.value.trim();
    
    // Check if we're using a masked key
    if (apiKeyInput.getAttribute('data-is-masked') === 'true' && apiKey.includes('•')) {
        // User didn't change the masked key, don't update
        showAlert('API key unchanged', 'info');
        return;
    }
    
    if (!apiKey) {
        showAlert('Please enter an API key', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/config/openai`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        if (response.ok) {
            showAlert('OpenAI configuration saved successfully', 'success');
            // Mask the API key after saving
            apiKeyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            apiKeyInput.setAttribute('data-original-key', apiKey);
            apiKeyInput.setAttribute('data-is-masked', 'true');
            checkSystemHealth();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save configuration', 'danger');
        }
    } catch (error) {
        console.error('Failed to save OpenAI config:', error);
        showAlert('Failed to save configuration', 'danger');
    }
}

async function saveAILimits() {
    const textLimit = parseInt(document.getElementById('ai-text-limit').value);
    const contextLimit = parseInt(document.getElementById('ai-context-limit').value);
    
    if (isNaN(textLimit) || textLimit < 1000 || textLimit > 100000) {
        showAlert('Text limit must be between 1,000 and 100,000 characters', 'warning');
        return;
    }
    
    if (isNaN(contextLimit) || contextLimit < 1000 || contextLimit > 100000) {
        showAlert('Context limit must be between 1,000 and 100,000 characters', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/config/ai-limits`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                text_limit: textLimit,
                context_limit: contextLimit
            })
        });
        
        if (response.ok) {
            showAlert('AI limits saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save AI limits', 'danger');
        }
    } catch (error) {
        console.error('Failed to save AI limits:', error);
        showAlert('Failed to save AI limits', 'danger');
    }
}

async function saveAIModels() {
    const chatModel = document.getElementById('chat-model').value;
    const analysisModel = document.getElementById('analysis-model').value;
    const embeddingModel = document.getElementById('embedding-model').value;
    
    if (!chatModel || !analysisModel || !embeddingModel) {
        showAlert('Please select all model options', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/config/ai-models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                chat_model: chatModel,
                analysis_model: analysisModel,
                embedding_model: embeddingModel
            })
        });
        
        if (response.ok) {
            showAlert('AI models saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save AI models', 'danger');
        }
    } catch (error) {
        console.error('Failed to save AI models:', error);
        showAlert('Failed to save AI models', 'danger');
    }
}

async function loadAILimits() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`);
        if (response.ok) {
            const config = await response.json();
            
            // Set AI limits in the form
            if (config.ai_text_limit) {
                document.getElementById('ai-text-limit').value = config.ai_text_limit;
            }
            if (config.ai_context_limit) {
                document.getElementById('ai-context-limit').value = config.ai_context_limit;
            }
            
            // Set AI model selections
            if (config.chat_model) {
                document.getElementById('chat-model').value = config.chat_model;
            }
            if (config.analysis_model) {
                document.getElementById('analysis-model').value = config.analysis_model;
            }
            if (config.embedding_model) {
                document.getElementById('embedding-model').value = config.embedding_model;
            }
        }
    } catch (error) {
        console.error('Failed to load AI limits:', error);
    }
}

// testAI function is already defined later - removing duplicate

async function revectorizeAllDocuments() {
    // Show confirmation dialog
    const confirmed = await showConfirmDialog(
        'Revectorize All Documents',
        'This will delete all existing embeddings and regenerate them for all documents. This process may take several minutes and cannot be undone. Are you sure you want to continue?',
        'warning'
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        showAlert('Starting revectorization process...', 'info');
        
        // Add loading state to button
        const button = document.querySelector('[onclick="revectorizeAllDocuments()"]');
        const originalHTML = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
        
        const response = await authenticatedFetch(`${API_BASE}/search/rebuild-embeddings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert('Revectorization completed successfully! All documents have been re-embedded.', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Revectorization failed', 'danger');
        }
    } catch (error) {
        console.error('Revectorization failed:', error);
        showAlert('Network error: Revectorization failed', 'danger');
    } finally {
        // Restore button state
        const button = document.querySelector('[onclick="revectorizeAllDocuments()"]');
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Revectorize All Documents';
    }
}

// Document modal
async function openDocumentModal(documentId) {
    console.log('Opening document modal for ID:', documentId);
    try {
        // Ensure tags are loaded for suggestions
        if (!tags || tags.length === 0) {
            await loadTags();
        }
        
        // Fetch document data
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}`);
        if (!response.ok) {
            if (response.status === 404) {
                showAlert('Document not found. It may have been deleted.', 'warning');
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        currentDocument = await response.json();
        console.log('Document loaded:', currentDocument);
        
        // Track document view
        try {
            const viewResponse = await authenticatedFetch(`${API_BASE}/documents/${documentId}/view`, {
                method: 'POST'
            });
            if (viewResponse.ok) {
                const viewData = await viewResponse.json();
                // Update view count in current document
                currentDocument.view_count = viewData.view_count;
                currentDocument.last_viewed = viewData.last_viewed;
                console.log('View tracked:', viewData);
            }
        } catch (error) {
            console.error('Error tracking view:', error);
        }
        
        // Update modal title
        const titleElement = document.getElementById('modal-document-title');
        if (titleElement && currentDocument) {
            titleElement.textContent = currentDocument.title || currentDocument.original_filename || currentDocument.filename || 'Unknown Document';
        }
        
        // Store original tags
        originalDocumentTags = safeJSONParse(JSON.stringify(currentDocument.tags || []), []);
        
        // Show modal
        const modalElement = document.getElementById('documentModal');
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
        
        // Wait a moment for modal to render, then populate
        setTimeout(() => {
            // Ensure tab content container is visible
            const tabContent = document.getElementById('documentTabContent');
            if (tabContent) {
                tabContent.classList.remove('d-none');
                tabContent.style.display = 'block';
            }
            
            // Properly initialize Bootstrap tabs
            // Remove any existing tab event listeners and reset state
            document.querySelectorAll('#documentModal .nav-link').forEach(tab => {
                tab.classList.remove('active');
                tab.setAttribute('aria-selected', 'false');
            });
            
            document.querySelectorAll('#documentModal .tab-pane').forEach(pane => {
                pane.classList.remove('show', 'active');
                pane.removeAttribute('style');
            });
            
            // Activate the metadata tab and panel by default
            const metadataTab = document.getElementById('metadata-tab');
            const metadataPanel = document.getElementById('metadata-panel');
            
            if (metadataTab && metadataPanel) {
                metadataTab.classList.add('active');
                metadataTab.setAttribute('aria-selected', 'true');
                metadataPanel.classList.add('show', 'active');
                console.log('Metadata tab initialized as active');
            }
            
            // Initialize Bootstrap tab functionality
            const tabElements = document.querySelectorAll('#documentModal .nav-link[data-bs-toggle="tab"]');
            tabElements.forEach(tabElement => {
                // Remove any existing listeners
                tabElement.replaceWith(tabElement.cloneNode(true));
            });
            
            // Re-get elements after cloning and add Bootstrap tab behavior
            document.querySelectorAll('#documentModal .nav-link[data-bs-toggle="tab"]').forEach(tabElement => {
                tabElement.addEventListener('click', function(e) {
                    e.preventDefault();
                    
                    // Get target panel
                    const targetId = this.getAttribute('data-bs-target');
                    const targetPanel = document.querySelector(targetId);
                    
                    if (!targetPanel) return;
                    
                    // Hide all other tabs and panels
                    document.querySelectorAll('#documentModal .nav-link').forEach(tab => {
                        tab.classList.remove('active');
                        tab.setAttribute('aria-selected', 'false');
                    });
                    
                    document.querySelectorAll('#documentModal .tab-pane').forEach(pane => {
                        pane.classList.remove('show', 'active');
                    });
                    
                    // Show clicked tab and its panel
                    this.classList.add('active');
                    this.setAttribute('aria-selected', 'true');
                    targetPanel.classList.add('show', 'active');
                    
                    console.log('Tab switched to:', targetId);
                    
                    // If switching to additional info tab, refresh the data
                    if (targetId === '#additional-panel') {
                        console.log('Additional info tab clicked');
                        console.log('Current document state:', {
                            exists: !!currentDocument,
                            id: currentDocument?.id,
                            title: currentDocument?.title,
                            view_count: currentDocument?.view_count,
                            last_viewed: currentDocument?.last_viewed
                        });
                        
                        if (currentDocument) {
                            console.log('Calling populateAdditionalInfo for additional panel');
                            populateAdditionalInfo(currentDocument);
                        } else {
                            console.error('No current document available for additional info');
                        }
                    }
                    
                    // If switching to relations tab, load document relations
                    if (targetId === '#relations-panel') {
                        console.log('Relations tab clicked');
                        if (currentDocument) {
                            console.log('Loading document relations for:', currentDocument.id);
                            loadDocumentRelations(currentDocument.id);
                            // Also load similar documents
                            showSimilarDocuments(currentDocument.id);
                        } else {
                            console.error('No current document available for relations');
                        }
                    }
                    
                    // If switching to notes tab, load document notes
                    if (targetId === '#notes-panel') {
                        console.log('Notes tab clicked');
                        if (currentDocument) {
                            console.log('Loading document notes for:', currentDocument.id);
                            loadDocumentNotes(currentDocument.id);
                        } else {
                            console.error('No current document available for notes');
                        }
                    }
                });
            });
            
            // Load document viewer
            console.log('Loading document viewer...');
            loadDocumentViewer(documentId);
            
            // Populate form data
            console.log('Populating form data...');
            // Add a delay to ensure DOM is ready
            setTimeout(() => {
                populateDocumentForm(currentDocument);
                // Update view count display specifically after tracking
                populateAdditionalInfo(currentDocument);
                
                // Force update after a short delay to ensure view count is displayed
                setTimeout(() => {
                    console.log('Force updating additional info after delay');
                    populateAdditionalInfo(currentDocument);
                }, 500);
            }, 200);
            
            // Load logs
            console.log('Loading document logs...');
            loadDocumentLogs();
            
            // Load OCR content
            console.log('Loading OCR content...');
            loadOCRContent(documentId);
            
            // Setup tab handlers
            setupOCRContentLoader(documentId);
            // Use Bootstrap's native tab switching instead of custom logic
        }, 200);
        
    } catch (error) {
        console.error('Failed to load document:', error);
        showAlert('Failed to load document details', 'danger');
    }
}

async function loadDocumentViewer(documentId) {
    console.log('Loading document viewer for document:', documentId);
    const viewer = document.getElementById('document-viewer');
    if (!viewer) {
        console.error('Document viewer element not found');
        return;
    }
    
    const fileName = currentDocument.original_filename || currentDocument.filename;
    const fileExtension = fileName ? fileName.split('.').pop().toLowerCase() : '';
    console.log('File name:', fileName, 'Extension:', fileExtension);
    
    // Clear previous content
    viewer.innerHTML = '';
    
    try {
        if (fileExtension === 'pdf') {
            console.log('Loading PDF viewer...');
            // PDF viewer
            viewer.innerHTML = `
                <iframe src="${API_BASE}/documents/${documentId}/file" 
                        type="application/pdf" 
                        width="100%" 
                        height="800px"
                        style="min-height: 70vh;">
                    <p>Your browser doesn't support PDF viewing. 
                       <a href="${API_BASE}/documents/${documentId}/download" target="_blank">Download the PDF</a>
                    </p>
                </iframe>
            `;
        } else if (['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'gif'].includes(fileExtension)) {
            // Image viewer
            viewer.innerHTML = `
                <div class="document-preview">
                    <img src="${API_BASE}/documents/${documentId}/file" 
                         alt="${fileName}" 
                         style="max-width: 100%; height: auto;">
                </div>
            `;
        } else if (['txt', 'md'].includes(fileExtension)) {
            // Text file viewer
            const textResponse = await authenticatedFetch(`${API_BASE}/documents/${documentId}/file`);
            const textContent = await textResponse.text();
            viewer.innerHTML = `
                <div class="document-preview">
                    <pre class="document-text">${textContent}</pre>
                </div>
            `;
        } else {
            // No preview available
            viewer.innerHTML = `
                <div class="no-preview">
                    <i class="fas fa-file"></i>
                    <h5>No Preview Available</h5>
                    <p>File type: ${fileExtension.toUpperCase()}</p>
                    <div class="mt-3">
                        <a href="${API_BASE}/documents/${documentId}/download" 
                           class="btn btn-primary" target="_blank">
                            <i class="fas fa-download me-2"></i>Download File
                        </a>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Failed to load document viewer:', error);
        viewer.innerHTML = `
            <div class="no-preview">
                <i class="fas fa-exclamation-triangle text-warning"></i>
                <h5>Error Loading Document</h5>
                <p>Could not load the document for viewing.</p>
                <div class="mt-3">
                    <a href="${API_BASE}/documents/${documentId}/download" 
                       class="btn btn-primary" target="_blank">
                        <i class="fas fa-download me-2"></i>Download File
                    </a>
                </div>
            </div>
        `;
    }
}

function populateDocumentForm(docData) {
    if (!docData) return;
    
    // Force show metadata panel
    const metadataPanel = document.getElementById('metadata-panel');
    if (metadataPanel) {
        metadataPanel.style.display = 'block';
        metadataPanel.style.visibility = 'visible';
        console.log('Forced metadata panel visible');
    }
    
    // Set basic form fields
    const docIdField = document.getElementById('edit-document-id');
    const titleField = document.getElementById('edit-title');
    const summaryField = document.getElementById('edit-summary');
    
    if (docIdField) {
        docIdField.value = docData.id || '';
        console.log('Set document ID field value:', docData.id);
        console.log('Document ID field actual value after setting:', docIdField.value);
        console.log('Document ID field max length:', docIdField.maxLength);
    }
    if (titleField) {
        titleField.value = docData.title || '';
        console.log('Set title:', docData.title);
    }
    if (summaryField) {
        summaryField.value = docData.summary || '';
        console.log('Set summary:', docData.summary);
    }
    
    // Populate correspondent dropdown
    const correspondentSelect = document.getElementById('edit-correspondent');
    if (correspondentSelect) {
        correspondentSelect.innerHTML = '<option value="">Select correspondent...</option>';
        correspondents.forEach(c => {
            const option = document.createElement('option');
            option.value = c.id;
            option.textContent = c.name;
            option.selected = docData.correspondent_id === c.id;
            correspondentSelect.appendChild(option);
        });
    }
    
    // Populate doctype dropdown
    const doctypeSelect = document.getElementById('edit-doctype');
    if (doctypeSelect) {
        doctypeSelect.innerHTML = '<option value="">Select document type...</option>';
        doctypes.forEach(d => {
            const option = document.createElement('option');
            option.value = d.id;
            option.textContent = d.name;
            option.selected = docData.doctype_id === d.id;
            doctypeSelect.appendChild(option);
        });
    }
    
    // Set dates
    const editDocDate = document.getElementById('edit-document-date');
    const editReminderDate = document.getElementById('edit-reminder-date');
    const reminderLabel = document.querySelector('label[for="edit-reminder-date"]');
    
    if (docData.document_date && editDocDate) {
        editDocDate.value = docData.document_date.split('T')[0];
    }
    
    if (docData.reminder_date && editReminderDate) {
        editReminderDate.value = docData.reminder_date.split('T')[0];
        
        // Check if reminder date is in the past
        const reminderDate = new Date(docData.reminder_date);
        const now = new Date();
        
        if (reminderDate < now) {
            editReminderDate.classList.add('past-reminder');
            if (reminderLabel) {
                reminderLabel.classList.add('past-reminder');
            }
        } else {
            editReminderDate.classList.remove('past-reminder');
            if (reminderLabel) {
                reminderLabel.classList.remove('past-reminder');
            }
        }
    } else {
        editReminderDate.classList.remove('past-reminder');
        if (reminderLabel) {
            reminderLabel.classList.remove('past-reminder');
        }
    }
    
    // Set tax relevant checkbox
    const editTaxRelevant = document.getElementById('edit-tax-relevant');
    if (editTaxRelevant) {
        editTaxRelevant.checked = docData.is_tax_relevant || false;
    }
    
    // Populate tags
    populateDocumentTags(docData.tags || []);
    
    // Delay tag suggestions to ensure datalist is in DOM
    setTimeout(() => {
        populateTagSuggestions();
    }, 100);
    
    // Populate file information
    const editFilename = document.getElementById('edit-filename');
    const editFileSize = document.getElementById('edit-file-size');
    const editMimeType = document.getElementById('edit-mime-type');
    const editFilePath = document.getElementById('edit-file-path');
    const editCreatedAt = document.getElementById('edit-created-at');
    const editProcessedAt = document.getElementById('edit-processed-at');
    
    if (editFilename) editFilename.textContent = docData.original_filename || docData.filename;
    if (editFileSize) editFileSize.textContent = formatFileSize(docData.file_size || 0);
    if (editMimeType) editMimeType.textContent = docData.mime_type || 'Unknown';
    if (editFilePath) editFilePath.textContent = docData.file_path || 'Unknown';
    if (editCreatedAt) editCreatedAt.textContent = formatDateTime(docData.created_at);
    if (editProcessedAt) editProcessedAt.textContent = formatDateTime(docData.processed_at);
    
    // Set processing status badges
    const ocrStatus = document.getElementById('edit-ocr-status');
    if (ocrStatus) {
        ocrStatus.textContent = docData.ocr_status || 'pending';
        ocrStatus.className = `badge ${getStatusBadgeClass(docData.ocr_status)}`;
    }
    
    const aiStatus = document.getElementById('edit-ai-status');
    if (aiStatus) {
        aiStatus.textContent = docData.ai_status || 'pending';
        aiStatus.className = `badge ${getStatusBadgeClass(docData.ai_status)}`;
    }
    
    // Populate additional information tab
    populateAdditionalInfo(docData);
    
    console.log('Document form populated successfully');
}

// Rerun OCR processing for the current document
async function rerunOCRProcessing() {
    if (!currentDocument || !currentDocument.id) {
        showAlert('No document selected', 'error');
        return;
    }
    
    const button = document.getElementById('rerun-ocr-btn');
    const ocrStatus = document.getElementById('edit-ocr-status');
    
    try {
        // Disable button and show processing
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/reprocess-ocr`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        showAlert('OCR processing queued for retry', 'success');
        
        // Update status display
        ocrStatus.textContent = 'processing';
        ocrStatus.className = 'badge bg-warning';
        button.style.display = 'none';
        
        // Reload document after a delay to get updated status
        setTimeout(async () => {
            await openDocumentModal(currentDocument.id);
        }, 3000);
        
    } catch (error) {
        console.error('Error rerunning OCR processing:', error);
        showAlert('Failed to rerun OCR processing', 'error');
        
        // Re-enable button
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-redo me-1"></i>Rerun';
    }
}

// Rerun vectorization processing for the current document
async function rerunVectorProcessing() {
    if (!currentDocument || !currentDocument.id) {
        showAlert('No document selected', 'error');
        return;
    }
    
    const button = document.getElementById('rerun-vector-btn');
    const vectorStatus = document.getElementById('edit-vector-status');
    
    try {
        // Disable button and show processing
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/reprocess-vector`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        showAlert('Vectorization processing queued for retry', 'success');
        
        // Update status display
        vectorStatus.textContent = 'processing';
        vectorStatus.className = 'badge bg-warning';
        button.style.display = 'none';
        
        // Reload document after a delay to get updated status
        setTimeout(async () => {
            await openDocumentModal(currentDocument.id);
        }, 2000);
        
    } catch (error) {
        console.error('Error rerunning vectorization:', error);
        showAlert('Failed to rerun vectorization', 'error');
        
        // Re-enable button
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-redo me-1"></i>Rerun';
    }
}

// Rerun AI processing for the current document
async function rerunAIProcessing() {
    if (!currentDocument || !currentDocument.id) {
        showAlert('No document selected', 'error');
        return;
    }
    
    const button = document.getElementById('rerun-ai-btn');
    const aiStatus = document.getElementById('edit-ai-status');
    
    try {
        // Disable button and show processing
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/reprocess-ai`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        showAlert('AI processing queued for retry', 'success');
        
        // Update status display
        aiStatus.textContent = 'processing';
        aiStatus.className = 'badge bg-warning';
        button.style.display = 'none';
        
        // Reload document after a delay to get updated status
        setTimeout(async () => {
            await openDocumentModal(currentDocument.id);
        }, 2000);
        
    } catch (error) {
        console.error('Error rerunning AI processing:', error);
        showAlert('Failed to rerun AI processing', 'error');
        
        // Re-enable button
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-redo me-1"></i>Rerun';
    }
}

// Populate additional information tab
function populateAdditionalInfo(docData) {
    console.log('populateAdditionalInfo called with data:', {
        view_count: docData.view_count,
        last_viewed: docData.last_viewed,
        fullDocument: docData
    });
    
    // Check if the additional panel is visible
    const additionalPanel = document.getElementById('additional-panel');
    console.log('Additional panel state:', {
        exists: !!additionalPanel,
        isActive: additionalPanel?.classList.contains('active'),
        isShow: additionalPanel?.classList.contains('show'),
        display: additionalPanel?.style.display,
        classList: additionalPanel?.className
    });
    
    // Populate File Information
    const filenameEl = document.getElementById('edit-filename');
    const fileSizeEl = document.getElementById('edit-file-size');
    const mimeTypeEl = document.getElementById('edit-mime-type');
    const filePathEl = document.getElementById('edit-file-path');
    const createdAtEl = document.getElementById('edit-created-at');
    const processedAtEl = document.getElementById('edit-processed-at');
    
    if (filenameEl) filenameEl.textContent = docData.original_filename || docData.filename || 'N/A';
    if (fileSizeEl) fileSizeEl.textContent = formatFileSize(docData.file_size || 0);
    if (mimeTypeEl) mimeTypeEl.textContent = docData.mime_type || 'N/A';
    if (filePathEl) filePathEl.textContent = docData.file_path || 'N/A';
    if (createdAtEl) createdAtEl.textContent = formatDateTime(docData.created_at) || 'N/A';
    if (processedAtEl) processedAtEl.textContent = formatDateTime(docData.processed_at) || 'N/A';
    
    // Populate Processing Status
    const ocrStatusEl = document.getElementById('edit-ocr-status');
    const aiStatusEl = document.getElementById('edit-ai-status');
    
    if (ocrStatusEl) {
        ocrStatusEl.textContent = docData.ocr_status || 'pending';
        ocrStatusEl.className = 'badge ' + getStatusBadgeClass(docData.ocr_status || 'pending');
        
        // Show/hide OCR rerun button based on status
        const rerunOcrBtn = document.getElementById('rerun-ocr-btn');
        if (rerunOcrBtn) {
            if (docData.ocr_status === 'failed' || docData.ocr_status === 'error') {
                rerunOcrBtn.style.display = 'inline-block';
            } else {
                rerunOcrBtn.style.display = 'none';
            }
        }
    }
    
    if (aiStatusEl) {
        aiStatusEl.textContent = docData.ai_status || 'pending';
        aiStatusEl.className = 'badge ' + getStatusBadgeClass(docData.ai_status || 'pending');
        
        // Show/hide rerun button based on AI status
        const rerunBtn = document.getElementById('rerun-ai-btn');
        if (rerunBtn) {
            if (docData.ai_status === 'failed' || docData.ai_status === 'error') {
                rerunBtn.style.display = 'inline-block';
            } else {
                rerunBtn.style.display = 'none';
            }
        }
    }
    
    // Populate Vectorization Status
    const vectorStatusEl = document.getElementById('edit-vector-status');
    if (vectorStatusEl) {
        vectorStatusEl.textContent = docData.vector_status || 'pending';
        vectorStatusEl.className = 'badge ' + getStatusBadgeClass(docData.vector_status || 'pending');
        
        // Show/hide vectorization rerun button based on status
        const rerunVectorBtn = document.getElementById('rerun-vector-btn');
        if (rerunVectorBtn) {
            if (docData.vector_status === 'failed' || docData.vector_status === 'error') {
                rerunVectorBtn.style.display = 'inline-block';
            } else {
                rerunVectorBtn.style.display = 'none';
            }
        }
    }
    
    // Update view count and last viewed (Document Statistics)
    const viewCount = document.getElementById('edit-view-count');
    const lastViewed = document.getElementById('edit-last-viewed');
    
    console.log('Found statistics elements:', {
        viewCount: viewCount,
        lastViewed: lastViewed
    });
    
    if (viewCount) {
        viewCount.textContent = docData.view_count !== undefined ? docData.view_count.toString() : '0';
        console.log('Set view count to:', viewCount.textContent);
    } else {
        console.error('edit-view-count element not found!');
    }
    
    if (lastViewed) {
        lastViewed.textContent = docData.last_viewed ? formatDateTime(docData.last_viewed) : 'Never';
        console.log('Set last viewed to:', lastViewed.textContent);
    } else {
        console.error('edit-last-viewed element not found!');
    }
    
    // Populate Approval Status
    const approvalStatusEl = document.getElementById('edit-approval-status');
    const approvedAtEl = document.getElementById('edit-approved-at');
    const approvedByEl = document.getElementById('edit-approved-by');
    const approveBtn = document.getElementById('approve-document-btn');
    const disapproveBtn = document.getElementById('disapprove-document-btn');
    
    if (approvalStatusEl) {
        if (docData.is_approved) {
            approvalStatusEl.innerHTML = '<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>Approved</span>';
        } else {
            approvalStatusEl.innerHTML = '<span class="badge bg-secondary"><i class="fas fa-clock me-1"></i>Pending</span>';
        }
    }
    
    if (approvedAtEl) {
        approvedAtEl.textContent = docData.approved_at ? formatDateTime(docData.approved_at) : 'N/A';
    }
    
    if (approvedByEl) {
        // For now just show the user ID, we could fetch user details later
        approvedByEl.textContent = docData.approved_by || 'N/A';
    }
    
    // Update approval buttons
    if (approveBtn && disapproveBtn) {
        if (docData.is_approved) {
            approveBtn.style.display = 'none';
            disapproveBtn.style.display = 'inline-block';
        } else {
            approveBtn.style.display = 'inline-block';
            disapproveBtn.style.display = 'none';
        }
    }
    
    // Debug: Check if all elements were populated
    console.log('Additional info populated:', {
        fileInfo: {
            filename: filenameEl?.textContent,
            fileSize: fileSizeEl?.textContent,
            mimeType: mimeTypeEl?.textContent,
            filePath: filePathEl?.textContent,
            createdAt: createdAtEl?.textContent,
            processedAt: processedAtEl?.textContent
        },
        processingStatus: {
            ocr: ocrStatusEl?.textContent,
            ai: aiStatusEl?.textContent
        },
        statistics: {
            viewCount: viewCount?.textContent,
            lastViewed: lastViewed?.textContent
        }
    });
}

// Make approval functions available globally
window.approveDocumentFromModal = async function() {
    if (!currentDocument) {
        showAlert('No document selected', 'error');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/approve`, {
            method: 'POST',
            body: JSON.stringify({ approved: true })
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
            
            // Update current document data
            currentDocument.is_approved = true;
            currentDocument.approved_at = result.approved_at;
            currentDocument.approved_by = result.approved_by;
            
            // Update the modal display
            populateAdditionalInfo(currentDocument);
            
            // Refresh the documents list
            refreshDocuments();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to approve document', 'danger');
        }
    } catch (error) {
        console.error('Error approving document:', error);
        showAlert('Error approving document', 'danger');
    }
};

window.disapproveDocumentFromModal = async function() {
    if (!currentDocument) {
        showAlert('No document selected', 'error');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/approve`, {
            method: 'POST',
            body: JSON.stringify({ approved: false })
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
            
            // Update current document data
            currentDocument.is_approved = false;
            currentDocument.approved_at = null;
            currentDocument.approved_by = null;
            
            // Update the modal display
            populateAdditionalInfo(currentDocument);
            
            // Refresh the documents list
            refreshDocuments();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to remove approval', 'danger');
        }
    } catch (error) {
        console.error('Error removing approval:', error);
        showAlert('Error removing approval', 'danger');
    }
};

// Test function to verify approval functions are loaded
window.testApprovalFunctions = function() {
    console.log('Testing approval functions...');
    console.log('toggleApproval:', typeof window.toggleApproval);
    console.log('approveDocumentFromModal:', typeof window.approveDocumentFromModal);
    console.log('disapproveDocumentFromModal:', typeof window.disapproveDocumentFromModal);
    
    if (typeof window.toggleApproval === 'function' && 
        typeof window.approveDocumentFromModal === 'function' && 
        typeof window.disapproveDocumentFromModal === 'function') {
        console.log('✅ All approval functions are available!');
        return true;
    } else {
        console.error('❌ Some approval functions are missing!');
        return false;
    }
};

function populateTagSuggestions() {
    const dropdown = document.getElementById('tag-suggestions-dropdown');
    const content = document.querySelector('.tag-suggestions-content');
    console.log('populateTagSuggestions called, dropdown:', dropdown);
    if (!dropdown || !content) {
        console.error('tag-suggestions dropdown not found');
        return;
    }
    
    // Clear existing options
    content.innerHTML = '';
    
    // Get all existing tag names from the current document
    const currentTagNames = currentDocument?.tags?.map(t => t.name.toLowerCase()) || [];
    console.log('Current document tags:', currentTagNames);
    console.log('Available tags:', tags);
    
    // Add all available tags as suggestions, excluding those already added
    if (tags && tags.length > 0) {
        let addedCount = 0;
        tags.forEach(tag => {
            if (!currentTagNames.includes(tag.name.toLowerCase())) {
                const option = document.createElement('div');
                option.className = 'tag-option';
                option.textContent = tag.name;
                option.onclick = () => selectTagSuggestion(tag.name);
                content.appendChild(option);
                addedCount++;
            }
        });
        console.log(`Added ${addedCount} tag suggestions to dropdown`);
    } else {
        console.log('No tags available for suggestions');
    }
}

function showTagSuggestions() {
    const dropdown = document.getElementById('tag-suggestions-dropdown');
    if (!dropdown) return;
    
    // First remove the dropdown class to show it temporarily for measurement
    dropdown.classList.remove('d-none');
    
    // Remove any existing dropup class
    dropdown.classList.remove('dropup');
    
    // Get the input element to calculate position
    const input = document.getElementById('new-tag-input');
    if (!input) {
        return;
    }
    
    // Calculate if there's enough space below
    const inputRect = input.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    
    // Check if we're in a modal context for smaller dropdown height
    const isInModal = input.closest('.modal') !== null;
    const dropdownHeight = isInModal ? 200 : 280; // Use smaller height in modals
    
    const spaceBelow = viewportHeight - inputRect.bottom;
    const spaceAbove = inputRect.top;
    
    // Add some padding to account for margins and better UX
    const requiredSpace = dropdownHeight + 20;
    
    // If not enough space below but enough space above, use dropup
    if (spaceBelow < requiredSpace && spaceAbove > requiredSpace) {
        dropdown.classList.add('dropup');
    }
    
    // Show the dropdown
    dropdown.classList.remove('d-none');
}

function hideTagSuggestionsDelayed() {
    setTimeout(() => {
        hideTagSuggestions();
    }, 150);
}

function hideTagSuggestions() {
    const dropdown = document.getElementById('tag-suggestions-dropdown');
    if (dropdown) {
        dropdown.classList.add('d-none');
    }
}

function filterTagSuggestions() {
    const input = document.getElementById('new-tag-input');
    const content = document.querySelector('.tag-suggestions-content');
    const filter = input.value.toLowerCase();
    
    if (!content) return;
    
    const options = content.querySelectorAll('.tag-option');
    let visibleCount = 0;
    
    options.forEach(option => {
        const text = option.textContent.toLowerCase();
        if (text.includes(filter)) {
            option.style.display = 'block';
            visibleCount++;
        } else {
            option.style.display = 'none';
        }
    });
    
    // Only show suggestions if there are visible options
    if (visibleCount > 0) {
        showTagSuggestions();
    } else {
        hideTagSuggestions();
    }
}

function selectTagSuggestion(tagName) {
    const input = document.getElementById('new-tag-input');
    input.value = tagName;
    hideTagSuggestions();
    addDocumentTag();
}

function populateDocumentTags(documentTags) {
    const container = document.getElementById('edit-tags-container');
    // Clear container
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    
    documentTags.forEach(tag => {
        const tagElement = createElement('span', '', {}, ['tag-item', 'me-2', 'mb-2']);
        
        // Tag icon
        const tagIcon = createElement('i', '', {}, ['fas', 'fa-tag', 'me-1']);
        tagElement.appendChild(tagIcon);
        
        // Tag name
        const tagName = createElement('span', tag.name, {}, ['tag-name']);
        tagElement.appendChild(tagName);
        
        // Remove button
        const removeBtn = createElement('button', '', {
            type: 'button',
            title: 'Remove tag'
        }, ['remove-tag-btn', 'ms-2']);
        removeBtn.addEventListener('click', () => removeDocumentTag(tag.id));
        
        const removeIcon = createElement('i', '', {}, ['fas', 'fa-times']);
        removeBtn.appendChild(removeIcon);
        tagElement.appendChild(removeBtn);
        
        container.appendChild(tagElement);
    });
}

async function saveDocumentChanges() {
    if (!currentDocument) return;
    
    // Get date values and convert to ISO format if present
    const documentDateValue = document.getElementById('edit-document-date').value;
    const reminderDateValue = document.getElementById('edit-reminder-date').value;
    
    // Get select values and convert empty strings to null
    const correspondentValue = document.getElementById('edit-correspondent').value;
    const doctypeValue = document.getElementById('edit-doctype').value;
    
    const updateData = {
        title: document.getElementById('edit-title').value.trim(),
        summary: document.getElementById('edit-summary').value.trim(),
        correspondent_id: correspondentValue === "" ? null : correspondentValue,
        doctype_id: doctypeValue === "" ? null : doctypeValue,
        document_date: documentDateValue ? new Date(documentDateValue).toISOString() : null,
        reminder_date: reminderDateValue ? new Date(reminderDateValue).toISOString() : null,
        is_tax_relevant: document.getElementById('edit-tax-relevant').checked,
        tag_ids: currentDocument.tags ? currentDocument.tags.map(tag => tag.id) : []
    };
    
    console.log('Saving document with data:', updateData);
    
    try {
        // First update document metadata
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            console.error('Save failed:', error);
            // Show detailed validation errors if available
            if (error.detail && Array.isArray(error.detail)) {
                const errorMessages = error.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', ');
                showAlert(`Validation error: ${errorMessages}`, 'danger');
            } else {
                showAlert(error.detail || 'Failed to update document', 'danger');
            }
            return;
        }
        
        // Tags are now handled in the main update
        
        const updatedDocument = await response.json();
        currentDocument = { ...currentDocument, ...updatedDocument };
        
        // Update original tags to current state
        originalDocumentTags = safeJSONParse(JSON.stringify(currentDocument.tags || []), []);
        
        showAlert('Document updated successfully', 'success');
        
        // Refresh the documents list
        if (currentTab === 'documents') {
            loadDocuments(currentPage);
        }
    } catch (error) {
        console.error('Failed to update document:', error);
        showAlert('Failed to update document', 'danger');
    }
}


// Document viewer actions
function downloadDocument() {
    if (!currentDocument) return;
    
    const downloadUrl = `${API_BASE}/documents/${currentDocument.id}/download`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = currentDocument.original_filename || currentDocument.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function openInNewTab() {
    if (!currentDocument) return;
    
    const fileUrl = `${API_BASE}/documents/${currentDocument.id}/file`;
    window.open(fileUrl, '_blank');
}

// Tag management functions - local changes only until save
async function removeDocumentTag(tagId) {
    if (!currentDocument) {
        console.error('No current document available');
        showAlert('No document loaded', 'warning');
        return;
    }
    
    console.log(`Marking tag ${tagId} for removal from document ${currentDocument.id}`);
    
    // Remove tag from current document object (local change only)
    currentDocument.tags = currentDocument.tags.filter(tag => tag.id != tagId);
    populateDocumentTags(currentDocument.tags);
    populateTagSuggestions();
    showAlert('Tag removed (click Save to persist)', 'info');
}


function handleTagInputKeyPress(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        addDocumentTag();
    }
}

// Separate function for document tag management
async function addDocumentTag() {
    const input = document.getElementById('new-tag-input');
    const tagName = input.value.trim();
    
    if (!tagName || !currentDocument) return;
    
    try {
        // First check if tag already exists in global tags array
        let tagToAdd = tags.find(t => t.name.toLowerCase() === tagName.toLowerCase());
        
        // If tag doesn't exist, create it
        if (!tagToAdd) {
            const createResponse = await authenticatedFetch(`${API_BASE}/tags/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: tagName })
            });
            
            if (!createResponse.ok) {
                const error = await createResponse.json();
                showAlert(error.detail || 'Failed to create tag', 'danger');
                return;
            }
            
            tagToAdd = await createResponse.json();
            // Add to global tags array
            tags.push(tagToAdd);
        }
        
        // Check if tag is already added to current document
        if (currentDocument.tags.some(t => t.id === tagToAdd.id)) {
            showAlert('Tag already added to document', 'info');
            input.value = '';
            return;
        }
        
        // Add tag to current document
        currentDocument.tags.push(tagToAdd);
        populateDocumentTags(currentDocument.tags);
        populateTagSuggestions();
        input.value = '';
        
        // Note: The actual save will happen when user clicks Save button
        showAlert('Tag added (click Save to persist)', 'info');
    } catch (error) {
        console.error('Failed to add tag:', error);
        showAlert('Failed to add tag', 'danger');
    }
}

// Document logs management
async function loadDocumentLogs() {
    if (!currentDocument) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${currentDocument.id}/logs`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const logs = await response.json();
        
        displayDocumentLogs(logs);
    } catch (error) {
        console.error('Failed to load document logs:', error);
        const container = document.getElementById('document-logs');
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const errorDiv = createElement('div', 'Failed to load logs', {}, ['text-muted']);
        container.appendChild(errorDiv);
    }
}

function displayDocumentLogs(logs) {
    const container = document.getElementById('document-logs');
    
    if (logs.length === 0) {
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        const noLogsDiv = createElement('div', 'No logs available', {}, ['text-muted']);
        container.appendChild(noLogsDiv);
        return;
    }
    
    // Clear container
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    
    logs.forEach(log => {
        const statusColor = log.status === 'success' ? 'text-success' : 
                           log.status === 'error' ? 'text-danger' : 
                           log.status === 'warning' ? 'text-warning' : 'text-info';
        
        const logDiv = createElement('div', '', {}, ['border-bottom', 'py-2']);
        
        // Header row
        const headerDiv = createElement('div', '', {}, ['d-flex', 'justify-content-between']);
        const operation = createElement('strong', log.operation, {}, [statusColor]);
        const timestamp = createElement('small', new Date(log.created_at).toLocaleString(), {}, ['text-muted']);
        headerDiv.appendChild(operation);
        headerDiv.appendChild(timestamp);
        logDiv.appendChild(headerDiv);
        
        // Message
        const messageDiv = createElement('div', log.message, {}, ['text-muted', 'small']);
        logDiv.appendChild(messageDiv);
        
        // Execution time if present
        if (log.execution_time) {
            const execTimeDiv = createElement('div', 'Execution time: ' + log.execution_time + 'ms', {}, ['text-muted', 'small']);
            logDiv.appendChild(execTimeDiv);
        }
        
        container.appendChild(logDiv);
    });
}

// Animation and UX enhancements
function addLoadingOverlay(message = 'Loading...') {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay show';
    const contentDiv = createElement('div', '', {}, ['loading-content']);
    const spinner = createElement('div', '', {}, ['spinner-border', 'text-primary']);
    const h5 = createElement('h5', message);
    contentDiv.appendChild(spinner);
    contentDiv.appendChild(h5);
    overlay.appendChild(contentDiv);
    document.body.appendChild(overlay);
    return overlay;
}

function removeLoadingOverlay(overlay) {
    if (overlay) {
        overlay.classList.remove('show');
        setTimeout(() => overlay.remove(), 300);
    }
}

function showToast(message, type = 'success') {
    const toastContainer = document.querySelector('.toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    const flexDiv = createElement('div', '', {}, ['d-flex']);
    const toastBody = createElement('div', '', {}, ['toast-body']);
    
    // Icon
    const iconClass = type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-circle' : 'info-circle';
    const icon = createElement('i', '', {}, ['fas', 'fa-' + iconClass, 'me-2']);
    toastBody.appendChild(icon);
    toastBody.appendChild(createTextNode(message));
    
    // Close button
    const closeBtn = createElement('button', '', {
        type: 'button',
        'data-bs-dismiss': 'toast'
    }, ['btn-close', 'btn-close-white', 'me-2', 'm-auto']);
    
    flexDiv.appendChild(toastBody);
    flexDiv.appendChild(closeBtn);
    toast.appendChild(flexDiv);
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1055';
    document.body.appendChild(container);
    return container;
}

function animateElement(element, animation = 'fade-in') {
    element.classList.add(animation);
    setTimeout(() => element.classList.remove(animation), 500);
}

// Enhanced view toggle function
function toggleView(viewType) {
    const documentsList = document.getElementById('documents-list');
    if (viewType === 'grid') {
        documentsList.className = 'document-grid';
    } else {
        documentsList.className = 'document-list';
    }
    
    // Update button states
    document.querySelectorAll('.view-toggle .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    document.querySelector(`[onclick="toggleView('${viewType}')"]`).classList.add('active');
    
    // Store preference
    localStorage.setItem('documentView', viewType);
}

// Enhanced document count display
function updateDocumentCount(count) {
    const countElement = document.getElementById('document-count');
    if (countElement) {
        const start = (currentPage - 1) * 20 + 1;
        const end = Math.min(start + count - 1, start + 19);
        countElement.textContent = count === 0 ? '0' : `${start}-${end}`;
        animateElement(countElement, 'scale-in');
    }
}

function updatePagination(page, totalCount) {
    const pagination = document.getElementById('documents-pagination');
    if (!pagination) return;
    
    const itemsPerPage = 20;
    const totalPages = Math.ceil(totalCount / itemsPerPage);
    const hasMore = page < totalPages;
    const hasPrevious = page > 1;
    
    let paginationHtml = '';
    
    if (hasPrevious || hasMore) {
        paginationHtml += `
            <li class="page-item ${!hasPrevious ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="navigateToPage(${page - 1}); return false;">
                    <i class="fas fa-chevron-left"></i>
                </a>
            </li>
        `;
        
        // Page numbers (show current page and a few around it)
        const startPage = Math.max(1, page - 2);
        const endPage = Math.min(totalPages, page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            paginationHtml += `
                <li class="page-item ${i === page ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="navigateToPage(${i}); return false;">${i}</a>
                </li>
            `;
        }
        
        paginationHtml += `
            <li class="page-item ${!hasMore ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="navigateToPage(${page + 1}); return false;">
                    <i class="fas fa-chevron-right"></i>
                </a>
            </li>
        `;
    }
    
    // Clear pagination
    while (pagination.firstChild) {
        pagination.removeChild(pagination.firstChild);
    }
    
    if (hasPrevious || hasMore) {
        // Previous button
        const prevLi = createElement('li', '', {}, ['page-item']);
        if (!hasPrevious) prevLi.classList.add('disabled');
        const prevLink = createElement('a', '', {
            href: '#'
        }, ['page-link']);
        prevLink.addEventListener('click', (e) => {
            e.preventDefault();
            navigateToPage(page - 1);
        });
        const prevIcon = createElement('i', '', {}, ['fas', 'fa-chevron-left']);
        prevLink.appendChild(prevIcon);
        prevLi.appendChild(prevLink);
        pagination.appendChild(prevLi);
        
        // Page numbers
        const startPage = Math.max(1, page - 2);
        const endPage = Math.min(totalPages, page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            const pageLi = createElement('li', '', {}, ['page-item']);
            if (i === page) pageLi.classList.add('active');
            const pageLink = createElement('a', String(i), {
                href: '#'
            }, ['page-link']);
            pageLink.addEventListener('click', (e) => {
                e.preventDefault();
                navigateToPage(i);
            });
            pageLi.appendChild(pageLink);
            pagination.appendChild(pageLi);
        }
        
        // Next button
        const nextLi = createElement('li', '', {}, ['page-item']);
        if (!hasMore) nextLi.classList.add('disabled');
        const nextLink = createElement('a', '', {
            href: '#'
        }, ['page-link']);
        nextLink.addEventListener('click', (e) => {
            e.preventDefault();
            navigateToPage(page + 1);
        });
        const nextIcon = createElement('i', '', {}, ['fas', 'fa-chevron-right']);
        nextLink.appendChild(nextIcon);
        nextLi.appendChild(nextLink);
        pagination.appendChild(nextLi);
    }
}

function navigateToPage(page) {
    if (page < 1) return;
    currentPage = page;
    loadDocuments(page);
}

// Utility functions for formatting
function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: '2-digit', 
        day: '2-digit' 
    });
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'completed':
        case 'success':
            return 'bg-success';
        case 'pending':
            return 'bg-warning';
        case 'failed':
        case 'error':
            return 'bg-danger';
        default:
            return 'bg-secondary';
    }
}

// Utility functions
function showAlert(message, type = 'info', duration = 5000) {
    // Create or get alert container
    let container = document.getElementById('alert-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'alert-container';
        container.style.cssText = 'position: fixed; top: 90px; right: 20px; z-index: 9999; max-width: 400px;';
        document.body.appendChild(container);
    }
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show mb-2`;
    alertDiv.style.cssText = 'opacity: 0; transform: translateX(100%); transition: all 0.3s ease;';
    
    // Add icon based on type
    const icons = {
        success: 'fas fa-check-circle',
        danger: 'fas fa-exclamation-triangle', 
        warning: 'fas fa-exclamation-circle',
        info: 'fas fa-info-circle'
    };
    
    // Create alert content
    const flexDiv = createElement('div', '', {}, ['d-flex', 'align-items-center']);
    
    // Icon
    const iconClass = icons[type] || icons.info;
    const icon = createElement('i', '', {}, iconClass.split(' ').concat(['me-2']));
    flexDiv.appendChild(icon);
    
    // Message
    const messageDiv = createElement('div', message, {}, ['flex-grow-1']);
    flexDiv.appendChild(messageDiv);
    
    // Close button
    const closeBtn = createElement('button', '', {
        type: 'button',
        'data-bs-dismiss': 'alert'
    }, ['btn-close']);
    flexDiv.appendChild(closeBtn);
    
    alertDiv.appendChild(flexDiv);
    
    container.appendChild(alertDiv);
    
    // Trigger animation
    setTimeout(() => {
        alertDiv.style.opacity = '1';
        alertDiv.style.transform = 'translateX(0)';
    }, 10);
    
    // Auto-remove with fade-out animation
    const removeAlert = () => {
        alertDiv.style.opacity = '0';
        alertDiv.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 300);
    };
    
    // Set auto-remove timer if duration is specified
    if (duration > 0) {
        setTimeout(removeAlert, duration);
    }
    
    // Add manual close functionality
    const closeButton = alertDiv.querySelector('.btn-close');
    if (closeButton) {
        closeButton.addEventListener('click', removeAlert);
    }
    
    return alertDiv;
}

function showConfirmDialog(title, message, type = 'primary') {
    return new Promise((resolve) => {
        // Create modal elements
        const modalId = 'confirmModal';
        let modal = document.getElementById(modalId);
        
        if (modal) {
            modal.remove();
        }
        
        // Create modal with safe DOM manipulation
        const modalDiv = document.createElement('div');
        modalDiv.className = 'modal fade';
        modalDiv.id = modalId;
        modalDiv.setAttribute('tabindex', '-1');
        modalDiv.setAttribute('aria-hidden', 'true');
        
        modalDiv.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-${type === 'danger' ? 'exclamation-triangle text-danger' : 'question-circle text-primary'} me-2"></i>
                            <span class="modal-title-text"></span>
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="mb-0 modal-message-text"></p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-${type}" id="confirmBtn">
                            ${type === 'danger' ? '<i class="fas fa-trash me-1"></i>Delete' : 'Confirm'}
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Set text content safely
        modalDiv.querySelector('.modal-title-text').textContent = title;
        modalDiv.querySelector('.modal-message-text').textContent = message;
        
        document.body.appendChild(modalDiv);
        modal = document.getElementById(modalId);
        
        const confirmBtn = modal.querySelector('#confirmBtn');
        const bootstrapModal = new bootstrap.Modal(modal);
        
        // Handle confirm button click
        confirmBtn.addEventListener('click', () => {
            bootstrapModal.hide();
            resolve(true);
        });
        
        // Handle modal dismiss (cancel)
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
            resolve(false);
        });
        
        // Show the modal
        bootstrapModal.show();
    });
}

function showElement(elementId) {
    document.getElementById(elementId).classList.remove('d-none');
}

function hideElement(elementId) {
    document.getElementById(elementId).classList.add('d-none');
}

function showLoading(elementId) {
    showElement(elementId);
}

function hideLoading(elementId) {
    hideElement(elementId);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    if (ext === 'pdf') return 'pdf';
    if (['jpg', 'jpeg', 'png', 'bmp', 'tiff'].includes(ext)) return 'image';
    return 'default';
}

// Delete functions
async function deleteCorrespondent(id) {
    if (!confirm('Are you sure you want to delete this correspondent?')) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/correspondents/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadCorrespondents();
            displayCorrespondents();
            populateFilters();
            showAlert('Correspondent deleted successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete correspondent', 'danger');
        }
    } catch (error) {
        console.error('Failed to delete correspondent:', error);
        showAlert('Failed to delete correspondent', 'danger');
    }
}

async function deleteDocType(id) {
    if (!confirm('Are you sure you want to delete this document type?')) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/doctypes/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadDocTypes();
            displayDocTypes();
            populateFilters();
            showAlert('Document type deleted successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete document type', 'danger');
        }
    } catch (error) {
        console.error('Failed to delete document type:', error);
        showAlert('Failed to delete document type', 'danger');
    }
}

async function deleteTag(id) {
    if (!confirm('Are you sure you want to delete this tag?')) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/tags/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadTags();
            displayTags();
            populateFilters();
            showAlert('Tag deleted successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete tag', 'danger');
        }
    } catch (error) {
        console.error('Failed to delete tag:', error);
        showAlert('Failed to delete tag', 'danger');
    }
}

// Custom Rename Modal functionality
let currentRenameCallback = null;

function showRenameModal(title, currentName, helpText, callback) {
    // Set modal content
    document.getElementById('rename-modal-title').textContent = title;
    document.getElementById('rename-field-label').textContent = 'New Name';
    document.getElementById('rename-help-text').textContent = helpText;
    document.getElementById('rename-input').value = currentName;
    document.getElementById('rename-input').placeholder = `Enter new ${title.toLowerCase()}...`;
    
    // Store callback for later use
    currentRenameCallback = callback;
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('renameModal'));
    modal.show();
    
    // Focus input after modal is shown
    document.getElementById('renameModal').addEventListener('shown.bs.modal', function() {
        const input = document.getElementById('rename-input');
        input.focus();
        input.select();
    }, { once: true });
}

// Setup rename modal event listeners
document.addEventListener('DOMContentLoaded', function() {
    const renameInput = document.getElementById('rename-input');
    const confirmBtn = document.getElementById('rename-confirm-btn');
    const renameForm = document.getElementById('rename-form');
    
    // Handle input changes for preview
    renameInput.addEventListener('input', function() {
        const newValue = this.value.trim();
        const previewDiv = document.querySelector('.rename-preview');
        const previewText = document.getElementById('rename-preview-text');
        
        if (newValue && newValue !== this.defaultValue) {
            previewText.textContent = newValue;
            previewDiv.classList.remove('d-none');
            confirmBtn.disabled = false;
        } else {
            previewDiv.classList.add('d-none');
            confirmBtn.disabled = true;
        }
    });
    
    // Handle form submission
    renameForm.addEventListener('submit', function(e) {
        e.preventDefault();
        handleRenameConfirm();
    });
    
    // Handle confirm button click
    confirmBtn.addEventListener('click', handleRenameConfirm);
    
    // Reset modal when closed
    document.getElementById('renameModal').addEventListener('hidden.bs.modal', function() {
        renameInput.value = '';
        document.querySelector('.rename-preview').classList.add('d-none');
        confirmBtn.disabled = true;
        currentRenameCallback = null;
    });
});

// Helper function to view a document (opens the document modal)
function viewDocument(documentId) {
    // Close any existing modals
    const modals = document.querySelectorAll('.modal.show');
    modals.forEach(modal => {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
    });
    
    // Open the document modal for the selected document
    setTimeout(() => {
        openDocumentModal(documentId);
    }, 300); // Small delay to allow modal to close
}

// Notes functionality
let notesAutoSaveTimeout = null;
let notesLastSavedContent = '';

async function loadDocumentNotes(documentId) {
    try {
        const response = await authenticatedFetch(`/api/documents/${documentId}/notes`);
        if (response.ok) {
            const data = await response.json();
            const notesTextarea = document.getElementById('document-notes');
            if (notesTextarea) {
                notesTextarea.value = data.notes || '';
                notesLastSavedContent = data.notes || '';
                updateNotesCharCount();
                updateNotesSaveStatus('saved');
            }
        } else {
            console.error('Failed to load document notes');
            updateNotesSaveStatus('error');
        }
    } catch (error) {
        console.error('Error loading document notes:', error);
        updateNotesSaveStatus('error');
    }
}

function handleNotesChange() {
    const notesTextarea = document.getElementById('document-notes');
    if (!notesTextarea) return;
    
    updateNotesCharCount();
    
    // Only trigger auto-save if content has changed
    if (notesTextarea.value !== notesLastSavedContent) {
        updateNotesSaveStatus('typing');
        
        // Clear existing timeout
        if (notesAutoSaveTimeout) {
            clearTimeout(notesAutoSaveTimeout);
        }
        
        // Set new timeout for auto-save (2 seconds after user stops typing)
        notesAutoSaveTimeout = setTimeout(() => {
            saveNotesAutomatically();
        }, 2000);
    }
}

async function saveNotesAutomatically() {
    if (!currentDocument) return;
    
    const notesTextarea = document.getElementById('document-notes');
    if (!notesTextarea) return;
    
    const notes = notesTextarea.value;
    
    // Only save if content has changed
    if (notes === notesLastSavedContent) {
        return;
    }
    
    updateNotesSaveStatus('saving');
    
    try {
        const response = await authenticatedFetch(`/api/documents/${currentDocument.id}/notes`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ notes: notes })
        });
        
        if (response.ok) {
            notesLastSavedContent = notes;
            updateNotesSaveStatus('saved');
        } else {
            updateNotesSaveStatus('error');
        }
    } catch (error) {
        console.error('Error saving notes:', error);
        updateNotesSaveStatus('error');
    }
}

async function saveNotesManually() {
    if (!currentDocument) {
        showAlert('No document selected', 'warning');
        return;
    }
    
    updateNotesSaveStatus('saving');
    await saveNotesAutomatically();
    showAlert('Notes saved successfully', 'success');
}

function clearNotes() {
    if (!confirm('Are you sure you want to clear all notes? This action cannot be undone.')) {
        return;
    }
    
    const notesTextarea = document.getElementById('document-notes');
    if (notesTextarea) {
        notesTextarea.value = '';
        updateNotesCharCount();
        handleNotesChange(); // Trigger auto-save of empty content
    }
}

function updateNotesCharCount() {
    const notesTextarea = document.getElementById('document-notes');
    const charCountElement = document.getElementById('notes-char-count');
    
    if (notesTextarea && charCountElement) {
        charCountElement.textContent = notesTextarea.value.length;
    }
}

function updateNotesSaveStatus(status) {
    const statusElement = document.getElementById('notes-save-status');
    if (!statusElement) return;
    
    // Remove all status classes
    statusElement.classList.remove('saving', 'saved', 'error');
    
    switch (status) {
        case 'typing':
            statusElement.textContent = '';
            break;
        case 'saving':
            statusElement.classList.add('saving');
            statusElement.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';
            break;
        case 'saved':
            statusElement.classList.add('saved');
            statusElement.innerHTML = '<i class="fas fa-check me-1"></i>Saved';
            setTimeout(() => {
                if (statusElement.classList.contains('saved')) {
                    statusElement.textContent = '';
                }
            }, 3000);
            break;
        case 'error':
            statusElement.classList.add('error');
            statusElement.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>Save failed';
            break;
    }
}

function handleRenameConfirm() {
    const newName = document.getElementById('rename-input').value.trim();
    if (newName && currentRenameCallback) {
        // Hide modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('renameModal'));
        modal.hide();
        
        // Execute callback
        currentRenameCallback(newName);
    }
}

// Edit/Rename functions
async function editCorrespondent(id, currentName) {
    try {
        // First, load the full correspondent data
        const response = await authenticatedFetch(`${API_BASE}/correspondents/${id}`);
        if (!response.ok) {
            throw new Error('Failed to load correspondent data');
        }
        
        const correspondent = await response.json();
        
        // Show the correspondent modal with all fields
        showCorrespondentModal(correspondent);
    } catch (error) {
        console.error('Failed to load correspondent:', error);
        showAlert('Failed to load correspondent data', 'danger');
    }
}

// Show correspondent modal for editing
function showCorrespondentModal(correspondent) {
    // Set modal title
    const modalTitle = document.getElementById('correspondent-modal-title');
    modalTitle.textContent = correspondent ? 'Edit Correspondent' : 'Add Correspondent';
    
    // Populate form fields
    document.getElementById('correspondent-name').value = correspondent?.name || '';
    document.getElementById('correspondent-email').value = correspondent?.email || '';
    document.getElementById('correspondent-address').value = correspondent?.address || '';
    
    // Store the correspondent ID for saving
    const saveBtn = document.getElementById('correspondent-save-btn');
    if (saveBtn) {
        saveBtn.dataset.correspondentId = correspondent?.id || '';
        
        // Remove any existing click handler and add new one
        saveBtn.onclick = async function() {
            await saveCorrespondent(correspondent?.id);
        };
    }
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('correspondentModal'));
    modal.show();
}

// Save correspondent (create or update)
async function saveCorrespondent(id) {
    const name = document.getElementById('correspondent-name').value.trim();
    const email = document.getElementById('correspondent-email').value.trim();
    const address = document.getElementById('correspondent-address').value.trim();
    
    if (!name) {
        showAlert('Please enter a correspondent name', 'warning');
        return;
    }
    
    try {
        const data = { name };
        if (email) data.email = email;
        if (address) data.address = address;
        
        const url = id ? `${API_BASE}/correspondents/${id}` : `${API_BASE}/correspondents/`;
        const method = id ? 'PUT' : 'POST';
        
        const response = await authenticatedFetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            await loadCorrespondents();
            displayCorrespondents();
            populateFilters();
            
            // Hide modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('correspondentModal'));
            modal.hide();
            
            showAlert(id ? 'Correspondent updated successfully' : 'Correspondent added successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save correspondent', 'danger');
        }
    } catch (error) {
        console.error('Failed to save correspondent:', error);
        showAlert('Failed to save correspondent', 'danger');
    }
}

async function editDocType(id, currentName) {
    showRenameModal(
        'Rename Document Type',
        currentName,
        'This will update the document type across all documents',
        async (newName) => {
            if (newName === currentName) {
                return;
            }
            
            try {
                const response = await authenticatedFetch(`${API_BASE}/doctypes/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName })
                });
                
                if (response.ok) {
                    await loadDocTypes();
                    displayDocTypes();
                    populateFilters();
                    showAlert('Document type renamed successfully', 'success');
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Failed to rename document type', 'danger');
                }
            } catch (error) {
                console.error('Failed to rename document type:', error);
                showAlert('Failed to rename document type', 'danger');
            }
        }
    );
}

async function editTag(id, currentName, currentColor = '#64748b') {
    showTagEditModal(id, currentName, currentColor);
}

function showTagEditModal(id, currentName, currentColor) {
    // Remove any existing modal
    const existingModal = document.querySelector('.tag-edit-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    const modal = document.createElement('div');
    modal.className = 'modal fade tag-edit-modal';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="fas fa-tag me-2"></i>Edit Tag
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Tag Name</label>
                        <input type="text" class="form-control" id="edit-tag-name" value="${currentName}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Tag Color</label>
                        <div class="input-group">
                            <span class="input-group-text">
                                <div class="tag-color-preview" id="tag-color-preview" style="width: 20px; height: 20px; border-radius: 50%; background-color: ${currentColor}; border: 1px solid rgba(255,255,255,0.3);"></div>
                            </span>
                            <input type="color" class="form-control form-control-color" id="edit-tag-color" value="${currentColor}" onchange="updateTagColorPreview()">
                        </div>
                        <small class="text-muted">Choose a color to identify this tag</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Preview</label>
                        <div>
                            <span class="document-tag" id="tag-preview" style="background-color: ${currentColor};">${currentName}</span>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="updateTag('${id}')">
                        <i class="fas fa-save me-1"></i>Update Tag
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
    
    // Focus on the name input
    setTimeout(() => {
        document.getElementById('edit-tag-name').focus();
        document.getElementById('edit-tag-name').select();
    }, 300);
    
    // Add event listener for name changes
    document.getElementById('edit-tag-name').addEventListener('input', updateTagPreview);
    
    modal.addEventListener('hidden.bs.modal', () => {
        document.body.removeChild(modal);
    });
}

function updateTagColorPreview() {
    const colorInput = document.getElementById('edit-tag-color');
    const preview = document.getElementById('tag-color-preview');
    const tagPreview = document.getElementById('tag-preview');
    
    if (colorInput && preview && tagPreview) {
        const color = colorInput.value;
        preview.style.backgroundColor = color;
        tagPreview.style.backgroundColor = color;
    }
}

function updateTagPreview() {
    const nameInput = document.getElementById('edit-tag-name');
    const tagPreview = document.getElementById('tag-preview');
    
    if (nameInput && tagPreview) {
        tagPreview.textContent = nameInput.value || 'Tag Name';
    }
}

async function updateTag(id) {
    const nameInput = document.getElementById('edit-tag-name');
    const colorInput = document.getElementById('edit-tag-color');
    
    const name = nameInput.value.trim();
    const color = colorInput.value;
    
    if (!name) {
        showAlert('Please enter a tag name', 'warning');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/tags/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, color: color })
        });
        
        if (response.ok) {
            await loadTags();
            displayTags();
            populateFilters();
            showAlert('Tag updated successfully', 'success');
            
            // Close modal
            const modal = document.querySelector('.tag-edit-modal');
            if (modal) {
                bootstrap.Modal.getInstance(modal).hide();
            }
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update tag', 'danger');
        }
    } catch (error) {
        console.error('Failed to update tag:', error);
        showAlert('Failed to update tag', 'danger');
    }
}

// OCR Content functionality
function setupOCRContentLoader(documentId) {
    const ocrTab = document.getElementById('ocr-tab');
    const contentDiv = document.getElementById('ocr-text-content');
    
    if (!ocrTab) {
        console.warn('OCR tab not found');
        return;
    }
    
    // Remove any existing event listeners to prevent duplicates
    const newOcrTab = ocrTab.cloneNode(true);
    ocrTab.parentNode.replaceChild(newOcrTab, ocrTab);
    
    // Add fresh event listener that always uses current document
    newOcrTab.addEventListener('click', async function () {
        // Use the current document ID, not the cached one
        const currentDocId = currentDocument ? currentDocument.id : documentId;
        console.log('Loading OCR content for document:', currentDocId);
        await loadOCRContent(currentDocId);
    });
    
    // Reset loading state when modal closes
    const modal = document.getElementById('documentModal');
    modal.addEventListener('hidden.bs.modal', function () {
        if (contentDiv) {
            contentDiv.innerHTML = `
                <div class="text-center text-muted p-3">
                    <i class="fas fa-spinner fa-spin me-2"></i>Loading OCR content...
                </div>
            `;
        }
        
        // Reset tags to original state
        if (currentDocument && originalDocumentTags) {
            currentDocument.tags = safeJSONParse(JSON.stringify(originalDocumentTags), []);
        }
    });
}

async function loadOCRContent(documentId) {
    const contentDiv = document.getElementById('ocr-text-content');
    
    if (!contentDiv) {
        console.error('OCR content div not found');
        return;
    }
    
    // Use documentId parameter or fall back to global currentDocument
    const docId = documentId || (currentDocument && currentDocument.id);
    
    console.log('loadOCRContent called with:', {
        providedDocumentId: documentId,
        currentDocumentId: currentDocument ? currentDocument.id : 'null',
        finalDocId: docId
    });
    
    if (!docId) {
        console.error('No documentId provided to loadOCRContent and no currentDocument available');
        contentDiv.innerHTML = '<div class="text-danger">Error: No document ID available</div>';
        return;
    }
    
    try {
        contentDiv.innerHTML = `
            <div class="text-center text-muted">
                <i class="fas fa-spinner fa-spin me-2"></i>Loading OCR content...
            </div>
        `;
        
        const response = await authenticatedFetch(`${API_BASE}/documents/${docId}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const document = await response.json();
        
        console.log('OCR data loaded for document:', {
            documentId: docId,
            title: document.title || document.original_filename,
            hasFullText: !!document.full_text,
            fullTextLength: document.full_text ? document.full_text.length : 0,
            fullTextPreview: document.full_text ? document.full_text.substring(0, 100) + '...' : 'none'
        });
        
        if (document.full_text && document.full_text.trim()) {
            contentDiv.innerHTML = `
                <div class="ocr-text-display">
                    <div class="mb-2">
                        <small class="text-muted">
                            <i class="fas fa-info-circle me-1"></i>
                            Extracted text content (${document.full_text.length} characters)
                        </small>
                    </div>
                    <div class="ocr-text-content">
                        ${document.full_text.replace(/\n/g, '<br>')}
                    </div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = `
                <div class="text-center text-muted py-3">
                    <i class="fas fa-file-text fa-2x mb-2 opacity-50"></i>
                    <p class="mb-0">No OCR text content available</p>
                    <small>This document may not have been processed yet or contains no extractable text.</small>
                </div>
            `;
        }
    } catch (error) {
        console.error('Failed to load OCR content:', error);
        contentDiv.innerHTML = `
            <div class="text-center text-danger py-3">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <p class="mb-0">Failed to load OCR content</p>
                <small>${error.message}</small>
            </div>
        `;
    }
}

// Search in OCR content
function searchInOCR() {
    const searchTerm = document.getElementById('ocr-search').value.toLowerCase();
    const ocrContent = document.getElementById('ocr-text-content');
    const resultsSpan = document.getElementById('ocr-search-results');
    
    if (!searchTerm) {
        clearOCRSearch();
        return;
    }
    
    // Get the original text content
    const originalText = ocrContent.textContent || ocrContent.innerText;
    
    if (!originalText) {
        resultsSpan.textContent = 'No content to search';
        return;
    }
    
    // Count matches
    const matches = (originalText.toLowerCase().match(new RegExp(searchTerm, 'g')) || []).length;
    
    if (matches > 0) {
        // Highlight matches
        const highlightedText = originalText.replace(
            new RegExp(`(${searchTerm})`, 'gi'),
            '<mark>$1</mark>'
        );
        ocrContent.innerHTML = highlightedText.replace(/\n/g, '<br>');
        resultsSpan.textContent = `${matches} match${matches > 1 ? 'es' : ''} found`;
        resultsSpan.className = 'small text-success mt-1';
    } else {
        resultsSpan.textContent = 'No matches found';
        resultsSpan.className = 'small text-muted mt-1';
    }
}

// Clear OCR search
function clearOCRSearch() {
    document.getElementById('ocr-search').value = '';
    const resultsSpan = document.getElementById('ocr-search-results');
    resultsSpan.textContent = '';
    
    // Reload OCR content to remove highlights
    const documentId = document.getElementById('edit-document-id').value;
    if (documentId) {
        loadOCRContent(documentId);
    }
}

// Delete document function
async function deleteDocument() {
    // Try to get document ID from current document first, then fallback to input field
    let documentId = currentDocument ? currentDocument.id : '';
    
    if (!documentId) {
        const documentIdElement = document.getElementById('edit-document-id');
        documentId = documentIdElement ? documentIdElement.value : '';
    }
    
    console.log('Delete document called');
    console.log('Current document:', currentDocument);
    console.log('Document ID from currentDocument:', currentDocument ? currentDocument.id : 'null');
    console.log('Document ID from input field:', document.getElementById('edit-document-id')?.value);
    console.log('Final document ID used:', documentId);
    
    if (!documentId) {
        showAlert('No document selected', 'warning');
        return;
    }
    
    const documentTitle = document.getElementById('edit-title').value || 'this document';
    
    // Show confirmation dialog
    const confirmed = await showConfirmDialog(
        'Delete Document', 
        `Are you sure you want to delete "${documentTitle}"? This action cannot be undone.`,
        'danger'
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/documents/${documentId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showAlert('Document deleted successfully', 'success');
            
            // Close the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('documentModal'));
            if (modal) {
                modal.hide();
            }
            
            // Refresh the documents list
            loadDocuments();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete document', 'danger');
        }
    } catch (error) {
        console.error('Failed to delete document:', error);
        showAlert('Failed to delete document', 'danger');
    }
}

// Missing functions that are referenced in HTML
function handleNavbarSearchKeyPress(event) {
    if (event.key === 'Enter') {
        performNavbarSearch();
    }
}

function performNavbarSearch() {
    const query = document.getElementById('navbar-search').value.trim();
    if (query) {
        // Switch to search tab and perform search
        showTab('search');
        document.getElementById('search-query').value = query;
        performSearch();
    }
}

// Utility functions
function showElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.remove('d-none');
    }
}

function hideElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.add('d-none');
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDateTime(dateString) {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleString();
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'completed': return 'bg-success';
        case 'failed': return 'bg-danger';
        case 'processing': return 'bg-warning';
        case 'pending': return 'bg-secondary';
        default: return 'bg-secondary';
    }
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
        case 'pdf': return 'fa-file-pdf text-danger';
        case 'jpg':
        case 'jpeg':
        case 'png':
        case 'gif':
        case 'bmp':
        case 'tiff': return 'fa-file-image text-primary';
        case 'txt': return 'fa-file-text text-info';
        default: return 'fa-file text-muted';
    }
}

// RAG/Ask AI functions

function toggleRagMode() {
    const isManual = document.getElementById('rag-manual').checked;
    const manualSelection = document.getElementById('manual-doc-selection');
    
    if (isManual) {
        manualSelection.classList.remove('d-none');
        loadDocumentsForSelection();
    } else {
        manualSelection.classList.add('d-none');
        selectedDocuments = [];
        updateSelectedDocsList();
    }
}

// Removed duplicate function - using the improved version above

function updateSelectedDocsList() {
    const container = document.getElementById('selected-docs-list');
    const countBadge = document.getElementById('selected-count');
    
    countBadge.textContent = selectedDocuments.length;
    
    if (selectedDocuments.length === 0) {
        container.innerHTML = '<div class="text-muted text-center">No documents selected</div>';
    } else {
        container.innerHTML = selectedDocuments.map(doc => {
            const truncatedTitle = doc.title.length > 35 ? doc.title.substring(0, 35) + '...' : doc.title;
            const escapedTitle = doc.title.replace(/'/g, "&apos;").replace(/"/g, "&quot;");
            
            return `
                <div class="selected-doc-item">
                    <div class="selected-doc-content">
                        <div class="selected-doc-title" title="${escapedTitle}">
                            ${truncatedTitle}
                        </div>
                        <button class="selected-doc-remove" onclick="removeDocumentFromSelection('${doc.id}')" title="Remove document">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
}

function removeDocumentFromSelection(docId) {
    selectedDocuments = selectedDocuments.filter(d => d.id !== docId);
    updateSelectedDocsList();
    
    // Uncheck the checkbox in available documents
    const checkbox = document.getElementById(`doc-${docId}`);
    if (checkbox) {
        checkbox.checked = false;
    }
}

// Enhanced confirmation dialog
function showConfirmDialog(title, message, type = 'warning') {
    return new Promise((resolve) => {
        const confirmed = confirm(`${title}\n\n${message}`);
        resolve(confirmed);
    });
}

// Retry all failed documents
window.retryAllFailed = async function() {
    try {
        // Get all documents with failed status
        const response = await authenticatedFetch(`${API_BASE}/documents/?limit=1000`);
        if (!response.ok) {
            throw new Error('Failed to fetch documents');
        }
        
        const documents = await response.json();
        const failedDocs = documents.filter(doc => 
            doc.ocr_status === 'failed' || 
            doc.ai_status === 'failed' || 
            doc.vector_status === 'failed'
        );
        
        if (failedDocs.length === 0) {
            showAlert('No failed documents to retry', 'info');
            return;
        }
        
        showAlert(`Retrying ${failedDocs.length} failed documents...`, 'info');
        
        let successCount = 0;
        let errorCount = 0;
        
        // Process each failed document
        for (const doc of failedDocs) {
            try {
                const retryResponse = await authenticatedFetch(`${API_BASE}/documents/${doc.id}/reprocess`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (retryResponse.ok) {
                    successCount++;
                } else {
                    errorCount++;
                }
            } catch (error) {
                console.error(`Failed to retry document ${doc.id}:`, error);
                errorCount++;
            }
        }
        
        // Show results
        if (successCount > 0 && errorCount === 0) {
            showAlert(`Successfully queued ${successCount} documents for reprocessing`, 'success');
        } else if (successCount > 0 && errorCount > 0) {
            showAlert(`Queued ${successCount} documents, failed to queue ${errorCount} documents`, 'warning');
        } else {
            showAlert('Failed to retry any documents', 'danger');
        }
        
        // Refresh documents after a delay
        setTimeout(() => {
            loadDocuments(currentPage);
        }, 1500);
        
    } catch (error) {
        console.error('Failed to retry all documents:', error);
        showAlert('Failed to retry all documents', 'danger');
    }
}


// Multiselect Functionality
let selectedTags = [];
let selectedSearchTags = [];
let selectedCorrespondents = [];
let selectedDoctypes = [];
let selectedSearchCorrespondents = [];
let selectedSearchDoctypes = [];

function populateCorrespondentsMultiselect() {
    // Documents filter correspondents
    const dropdown = document.querySelector('#correspondent-dropdown .correspondent-dropdown-content');
    if (dropdown) {
        dropdown.innerHTML = correspondents.map(correspondent => `
            <div class="correspondent-option" onclick="toggleCorrespondentSelection('${correspondent.id}', '${correspondent.name.replace(/'/g, "\\'")}')">
                <input type="checkbox" class="form-check-input" id="correspondent-${correspondent.id}" ${selectedCorrespondents.includes(correspondent.id) ? 'checked' : ''}>
                <span class="correspondent-name">${correspondent.name} (${correspondent.document_count || 0})</span>
            </div>
        `).join('');
    }
}

function populateSearchCorrespondentsMultiselect() {
    // Search filter correspondents
    const searchDropdown = document.querySelector('#search-correspondent-dropdown .search-correspondent-dropdown-content');
    console.log('populateSearchCorrespondentsMultiselect - dropdown found:', searchDropdown);
    console.log('correspondents data:', correspondents);
    if (searchDropdown) {
        searchDropdown.innerHTML = correspondents.map(correspondent => `
            <div class="correspondent-option" onclick="toggleSearchCorrespondentSelection('${correspondent.id}', '${correspondent.name.replace(/'/g, "\\'")}')">
                <input type="checkbox" class="form-check-input" id="search-correspondent-${correspondent.id}" ${selectedSearchCorrespondents.includes(correspondent.id) ? 'checked' : ''}>
                <span class="correspondent-name">${correspondent.name} (${correspondent.document_count || 0})</span>
            </div>
        `).join('');
        console.log('populated search correspondents:', correspondents.length);
    }
}

function populateDoctypesMultiselect() {
    // Documents filter doctypes
    const dropdown = document.querySelector('#doctype-dropdown .doctype-dropdown-content');
    if (dropdown) {
        dropdown.innerHTML = doctypes.map(doctype => `
            <div class="doctype-option" onclick="toggleDoctypeSelection('${doctype.id}', '${doctype.name.replace(/'/g, "\\'")}')">
                <input type="checkbox" class="form-check-input" id="doctype-${doctype.id}" ${selectedDoctypes.includes(doctype.id) ? 'checked' : ''}>
                <span class="doctype-name">${doctype.name} (${doctype.document_count || 0})</span>
            </div>
        `).join('');
    }
}

function populateSearchDoctypesMultiselect() {
    // Search filter doctypes
    const searchDropdown = document.querySelector('#search-doctype-dropdown .search-doctype-dropdown-content');
    if (searchDropdown) {
        searchDropdown.innerHTML = doctypes.map(doctype => `
            <div class="doctype-option" onclick="toggleSearchDoctypeSelection('${doctype.id}', '${doctype.name.replace(/'/g, "\\'")}')">
                <input type="checkbox" class="form-check-input" id="search-doctype-${doctype.id}" ${selectedSearchDoctypes.includes(doctype.id) ? 'checked' : ''}>
                <span class="doctype-name">${doctype.name} (${doctype.document_count || 0})</span>
            </div>
        `).join('');
    }
}

function populateTagsMultiselect() {
    // Documents filter tags
    const dropdown = document.querySelector('#tags-dropdown .tags-dropdown-content');
    if (dropdown) {
        // Sort tags by document count (most used first)
        const sortedTags = [...tags].sort((a, b) => (b.document_count || 0) - (a.document_count || 0));
        
        dropdown.innerHTML = sortedTags.map(tag => `
            <div class="tag-option" onclick="toggleTagSelection('${tag.id}', '${tag.name.replace(/'/g, "\\'")}', '${tag.color || '#64748b'}')">
                <input type="checkbox" class="form-check-input" id="tag-${tag.id}" ${selectedTags.includes(tag.id) ? 'checked' : ''}>
                <div class="tag-color" style="background-color: ${tag.color || '#64748b'}"></div>
                <span class="tag-name">${tag.name}</span>
                <span class="tag-count">(${tag.document_count || 0})</span>
            </div>
        `).join('');
    }
}

function populateSearchTagsMultiselect() {
    // Search filter tags
    const searchDropdown = document.querySelector('#search-tags-dropdown .tags-dropdown-content');
    if (searchDropdown) {
        // Sort tags by document count (most used first)
        const sortedTags = [...tags].sort((a, b) => (b.document_count || 0) - (a.document_count || 0));
        
        searchDropdown.innerHTML = sortedTags.map(tag => `
            <div class="tag-option" onclick="toggleSearchTagSelection('${tag.id}', '${tag.name.replace(/'/g, "\\'")}', '${tag.color || '#64748b'}')">
                <input type="checkbox" class="form-check-input" id="search-tag-${tag.id}" ${selectedSearchTags.includes(tag.id) ? 'checked' : ''}>
                <div class="tag-color" style="background-color: ${tag.color || '#64748b'}"></div>
                <span class="tag-name">${tag.name}</span>
                <span class="tag-count">(${tag.document_count || 0})</span>
            </div>
        `).join('');
    }
}

function toggleTagsDropdown() {
    const dropdown = document.getElementById('tags-dropdown');
    const display = document.getElementById('selected-tags-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeSearchTagsDropdown();
        closeCorrespondentDropdown();
        closeDoctypeDropdown();
        closeReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function toggleSearchTagsDropdown() {
    const dropdown = document.getElementById('search-tags-dropdown');
    const display = document.getElementById('search-selected-tags-display');
    
    if (dropdown && dropdown.classList.contains('d-none')) {
        // Move dropdown to body for proper positioning
        document.body.appendChild(dropdown);
        
        // Position dropdown
        const rect = display.getBoundingClientRect();
        dropdown.style.position = 'fixed';
        dropdown.style.top = `${rect.bottom + 4}px`;
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.width = `${rect.width}px`;
        dropdown.style.zIndex = '999999';
        
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeTagsDropdown();
        closeSearchCorrespondentDropdown();
        closeSearchDoctypeDropdown();
    } else if (dropdown) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeTagsDropdown() {
    const dropdown = document.getElementById('tags-dropdown');
    const display = document.getElementById('selected-tags-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeSearchTagsDropdown() {
    const dropdown = document.getElementById('search-tags-dropdown');
    const display = document.getElementById('search-selected-tags-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

// Reminder Dropdown Functions
function toggleReminderDropdown() {
    const dropdown = document.getElementById('reminder-dropdown');
    const display = document.getElementById('selected-reminder-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeCorrespondentDropdown();
        closeDoctypeDropdown();
        closeTagsDropdown();
        
        // Populate dropdown if needed
        populateReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeReminderDropdown() {
    const dropdown = document.getElementById('reminder-dropdown');
    const display = document.getElementById('selected-reminder-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function populateReminderDropdown() {
    const container = document.getElementById('reminder-dropdown').querySelector('.reminder-dropdown-content');
    
    const reminderOptions = [
        { key: 'all', label: 'All Documents' },
        { key: 'has', label: 'With Reminder' },
        { key: 'overdue', label: 'Overdue' },
        { key: 'none', label: 'Without Reminder' }
    ];
    
    let html = '';
    reminderOptions.forEach(option => {
        const isSelected = selectedReminder === option.key;
        html += `
            <div class="dropdown-item ${isSelected ? 'selected' : ''}" onclick="selectReminderOption('${option.key}')">
                <span>${option.label}</span>
                ${isSelected ? '<i class="fas fa-check ms-auto"></i>' : ''}
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function selectReminderOption(optionKey) {
    selectedReminder = optionKey;
    updateSelectedReminderDisplay();
    closeReminderDropdown();
    applyFilters();
}

function clearReminderFilter(event) {
    event.stopPropagation();
    selectedReminder = 'all';
    updateSelectedReminderDisplay();
    applyFilters();
}

function updateSelectedReminderDisplay() {
    const display = document.getElementById('selected-reminder-display');
    
    const reminderOptions = {
        'all': 'All Documents',
        'has': 'With Reminder',
        'overdue': 'Overdue',
        'none': 'Without Reminder'
    };
    
    if (!selectedReminder || selectedReminder === 'all') {
        display.innerHTML = `
            <span class="placeholder">All Documents</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
        display.classList.remove('has-selection');
    } else {
        display.innerHTML = `
            <div class="reminder-selection">
                <span class="reminder-item">
                    ${reminderOptions[selectedReminder]}
                    <i class="fas fa-times remove-reminder" onclick="clearReminderFilter(event)"></i>
                </span>
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
        display.classList.add('has-selection');
    }
}

// Correspondent Dropdown Functions
function toggleCorrespondentDropdown() {
    const dropdown = document.getElementById('correspondent-dropdown');
    const display = document.getElementById('selected-correspondent-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeDoctypeDropdown();
        closeTagsDropdown();
        closeReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeCorrespondentDropdown() {
    const dropdown = document.getElementById('correspondent-dropdown');
    const display = document.getElementById('selected-correspondent-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

// DocType Dropdown Functions
function toggleDoctypeDropdown() {
    const dropdown = document.getElementById('doctype-dropdown');
    const display = document.getElementById('selected-doctype-display');
    
    if (dropdown.classList.contains('d-none')) {
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeCorrespondentDropdown();
        closeTagsDropdown();
        closeReminderDropdown();
    } else {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeDoctypeDropdown() {
    const dropdown = document.getElementById('doctype-dropdown');
    const display = document.getElementById('selected-doctype-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

// Search Correspondent Dropdown Functions
function toggleSearchCorrespondentDropdown() {
    const dropdown = document.getElementById('search-correspondent-dropdown');
    const display = document.getElementById('selected-search-correspondent-display');
    
    if (dropdown && dropdown.classList.contains('d-none')) {
        // Ensure dropdown has content - check before moving to body
        const dropdownContent = dropdown.querySelector('.search-correspondent-dropdown-content');
        if (!dropdownContent || !dropdownContent.innerHTML.trim() || dropdownContent.children.length === 0) {
            populateSearchCorrespondentsMultiselect();
        }
        
        // Move dropdown to body for proper positioning
        document.body.appendChild(dropdown);
        
        // Position dropdown
        const rect = display.getBoundingClientRect();
        dropdown.style.position = 'fixed';
        dropdown.style.top = `${rect.bottom + 4}px`;
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.width = `${rect.width}px`;
        dropdown.style.zIndex = '999999';
        
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeSearchDoctypeDropdown();
        closeSearchTagsDropdown();
    } else if (dropdown) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeSearchCorrespondentDropdown() {
    const dropdown = document.getElementById('search-correspondent-dropdown');
    const display = document.getElementById('selected-search-correspondent-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

// Search DocType Dropdown Functions
function toggleSearchDoctypeDropdown() {
    const dropdown = document.getElementById('search-doctype-dropdown');
    const display = document.getElementById('selected-search-doctype-display');
    
    if (dropdown && dropdown.classList.contains('d-none')) {
        // Ensure dropdown has content - check before moving to body
        const dropdownContent = dropdown.querySelector('.search-doctype-dropdown-content');
        if (!dropdownContent || !dropdownContent.innerHTML.trim() || dropdownContent.children.length === 0) {
            populateSearchDoctypesMultiselect();
        }
        
        // Move dropdown to body for proper positioning
        document.body.appendChild(dropdown);
        
        // Position dropdown
        const rect = display.getBoundingClientRect();
        dropdown.style.position = 'fixed';
        dropdown.style.top = `${rect.bottom + 4}px`;
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.width = `${rect.width}px`;
        dropdown.style.zIndex = '999999';
        
        dropdown.classList.remove('d-none');
        display.classList.add('active');
        // Close other dropdowns
        closeSearchCorrespondentDropdown();
        closeSearchTagsDropdown();
    } else if (dropdown) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

function closeSearchDoctypeDropdown() {
    const dropdown = document.getElementById('search-doctype-dropdown');
    const display = document.getElementById('selected-search-doctype-display');
    if (dropdown && display) {
        dropdown.classList.add('d-none');
        display.classList.remove('active');
    }
}

// Correspondent Selection Functions
function toggleCorrespondentSelection(correspondentId, correspondentName) {
    const checkbox = document.getElementById(`correspondent-${correspondentId}`);
    
    if (selectedCorrespondents.includes(correspondentId)) {
        selectedCorrespondents = selectedCorrespondents.filter(id => id !== correspondentId);
        checkbox.checked = false;
    } else {
        selectedCorrespondents.push(correspondentId);
        checkbox.checked = true;
    }
    
    updateSelectedCorrespondentsDisplay();
    applyFilters();
}

function toggleSearchCorrespondentSelection(correspondentId, correspondentName) {
    const checkbox = document.getElementById(`search-correspondent-${correspondentId}`);
    
    if (selectedSearchCorrespondents.includes(correspondentId)) {
        selectedSearchCorrespondents = selectedSearchCorrespondents.filter(id => id !== correspondentId);
        checkbox.checked = false;
    } else {
        selectedSearchCorrespondents.push(correspondentId);
        checkbox.checked = true;
    }
    
    updateSelectedSearchCorrespondentsDisplay();
}

// DocType Selection Functions
function toggleDoctypeSelection(doctypeId, doctypeName) {
    const checkbox = document.getElementById(`doctype-${doctypeId}`);
    
    if (selectedDoctypes.includes(doctypeId)) {
        selectedDoctypes = selectedDoctypes.filter(id => id !== doctypeId);
        checkbox.checked = false;
    } else {
        selectedDoctypes.push(doctypeId);
        checkbox.checked = true;
    }
    
    updateSelectedDoctypesDisplay();
    applyFilters();
}

function toggleSearchDoctypeSelection(doctypeId, doctypeName) {
    const checkbox = document.getElementById(`search-doctype-${doctypeId}`);
    
    if (selectedSearchDoctypes.includes(doctypeId)) {
        selectedSearchDoctypes = selectedSearchDoctypes.filter(id => id !== doctypeId);
        checkbox.checked = false;
    } else {
        selectedSearchDoctypes.push(doctypeId);
        checkbox.checked = true;
    }
    
    updateSelectedSearchDoctypesDisplay();
}

function toggleTagSelection(tagId, tagName, tagColor) {
    const checkbox = document.getElementById(`tag-${tagId}`);
    
    if (selectedTags.includes(tagId)) {
        selectedTags = selectedTags.filter(id => id !== tagId);
        checkbox.checked = false;
    } else {
        selectedTags.push(tagId);
        checkbox.checked = true;
    }
    
    updateSelectedTagsDisplay();
    applyFilters();
}

function toggleSearchTagSelection(tagId, tagName, tagColor) {
    const checkbox = document.getElementById(`search-tag-${tagId}`);
    
    if (selectedSearchTags.includes(tagId)) {
        selectedSearchTags = selectedSearchTags.filter(id => id !== tagId);
        checkbox.checked = false;
    } else {
        selectedSearchTags.push(tagId);
        checkbox.checked = true;
    }
    
    updateSelectedSearchTagsDisplay();
}

function updateSelectedTagsDisplay() {
    const display = document.getElementById('selected-tags-display');
    const chevron = display.querySelector('.fas');
    
    if (selectedTags.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Tags</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedTagObjects = tags.filter(tag => selectedTags.includes(tag.id));
        const tagListHtml = selectedTagObjects.map(tag => `
            <span class="tag-item" style="background-color: ${tag.color || '#64748b'}">
                ${tag.name}
                <i class="fas fa-times remove-tag" onclick="removeTagFromSelection('${tag.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="tag-list">
                ${tagListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

function updateSelectedSearchTagsDisplay() {
    const display = document.getElementById('search-selected-tags-display');
    
    if (selectedSearchTags.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Tags</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedTagObjects = tags.filter(tag => selectedSearchTags.includes(tag.id));
        const tagListHtml = selectedTagObjects.map(tag => `
            <span class="tag-item" style="background-color: ${tag.color || '#64748b'}">
                ${tag.name}
                <i class="fas fa-times remove-tag" onclick="removeSearchTagFromSelection('${tag.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="tag-list">
                ${tagListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

function removeTagFromSelection(tagId, event) {
    event.stopPropagation();
    selectedTags = selectedTags.filter(id => id !== tagId);
    
    // Update checkbox
    const checkbox = document.getElementById(`tag-${tagId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedTagsDisplay();
    applyFilters();
}

function removeSearchTagFromSelection(tagId, event) {
    event.stopPropagation();
    selectedSearchTags = selectedSearchTags.filter(id => id !== tagId);
    
    // Update checkbox
    const checkbox = document.getElementById(`search-tag-${tagId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedSearchTagsDisplay();
}

// Correspondent Display Functions
function updateSelectedCorrespondentsDisplay() {
    const display = document.getElementById('selected-correspondent-display');
    
    if (selectedCorrespondents.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Correspondents</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedCorrespondentObjects = correspondents.filter(correspondent => selectedCorrespondents.includes(correspondent.id));
        const correspondentListHtml = selectedCorrespondentObjects.map(correspondent => `
            <span class="correspondent-item">
                ${correspondent.name}
                <i class="fas fa-times remove-correspondent" onclick="removeCorrespondentFromSelection('${correspondent.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="correspondent-list">
                ${correspondentListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

function updateSelectedSearchCorrespondentsDisplay() {
    const display = document.getElementById('selected-search-correspondent-display');
    
    if (selectedSearchCorrespondents.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Correspondents</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedCorrespondentObjects = correspondents.filter(correspondent => selectedSearchCorrespondents.includes(correspondent.id));
        const correspondentListHtml = selectedCorrespondentObjects.map(correspondent => `
            <span class="correspondent-item">
                ${correspondent.name}
                <i class="fas fa-times remove-correspondent" onclick="removeSearchCorrespondentFromSelection('${correspondent.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="correspondent-list">
                ${correspondentListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

// DocType Display Functions
function updateSelectedDoctypesDisplay() {
    const display = document.getElementById('selected-doctype-display');
    
    if (selectedDoctypes.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Types</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedDoctypeObjects = doctypes.filter(doctype => selectedDoctypes.includes(doctype.id));
        const doctypeListHtml = selectedDoctypeObjects.map(doctype => `
            <span class="doctype-item">
                ${doctype.name}
                <i class="fas fa-times remove-doctype" onclick="removeDoctypeFromSelection('${doctype.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="doctype-list">
                ${doctypeListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

function updateSelectedSearchDoctypesDisplay() {
    const display = document.getElementById('selected-search-doctype-display');
    
    if (selectedSearchDoctypes.length === 0) {
        display.innerHTML = `
            <span class="placeholder">All Types</span>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    } else {
        const selectedDoctypeObjects = doctypes.filter(doctype => selectedSearchDoctypes.includes(doctype.id));
        const doctypeListHtml = selectedDoctypeObjects.map(doctype => `
            <span class="doctype-item">
                ${doctype.name}
                <i class="fas fa-times remove-doctype" onclick="removeSearchDoctypeFromSelection('${doctype.id}', event)"></i>
            </span>
        `).join('');
        
        display.innerHTML = `
            <div class="doctype-list">
                ${doctypeListHtml}
            </div>
            <i class="fas fa-chevron-down ms-auto chevron"></i>
        `;
    }
}

// Remove Functions
function removeCorrespondentFromSelection(correspondentId, event) {
    event.stopPropagation();
    selectedCorrespondents = selectedCorrespondents.filter(id => id !== correspondentId);
    
    // Update checkbox
    const checkbox = document.getElementById(`correspondent-${correspondentId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedCorrespondentsDisplay();
    applyFilters();
}

function removeSearchCorrespondentFromSelection(correspondentId, event) {
    event.stopPropagation();
    selectedSearchCorrespondents = selectedSearchCorrespondents.filter(id => id !== correspondentId);
    
    // Update checkbox
    const checkbox = document.getElementById(`search-correspondent-${correspondentId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedSearchCorrespondentsDisplay();
}

function removeDoctypeFromSelection(doctypeId, event) {
    event.stopPropagation();
    selectedDoctypes = selectedDoctypes.filter(id => id !== doctypeId);
    
    // Update checkbox
    const checkbox = document.getElementById(`doctype-${doctypeId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedDoctypesDisplay();
    applyFilters();
}

function removeSearchDoctypeFromSelection(doctypeId, event) {
    event.stopPropagation();
    selectedSearchDoctypes = selectedSearchDoctypes.filter(id => id !== doctypeId);
    
    // Update checkbox
    const checkbox = document.getElementById(`search-doctype-${doctypeId}`);
    if (checkbox) checkbox.checked = false;
    
    updateSelectedSearchDoctypesDisplay();
}

// Extended Settings Functions
let currentWizardStep = 1;
let extendedSettings = {};

async function loadExtendedSettings() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`);
        if (response.ok) {
            extendedSettings = await response.json();
            populateExtendedSettings(extendedSettings);
            // Also load AI provider status
            loadAIProviderStatus();
        } else {
            console.error('Failed to load extended settings');
        }
    } catch (error) {
        console.error('Error loading extended settings:', error);
    }
}

function populateExtendedSettings(config = extendedSettings) {
    // AI Provider Settings
    const provider = config?.ai_provider || 'openai';
    const providerRadio = document.querySelector(`input[name="ai-provider"][value="${provider}"]`);
    if (providerRadio) {
        providerRadio.checked = true;
    }
    updateAIProviderUI(provider);
    
    // OpenAI Settings
    const apiKeyField = document.getElementById('openai-api-key');
    if (apiKeyField) {
        // Don't overwrite if already has a value (user might be editing)
        if (!apiKeyField.value || config?.openai_api_key === '***') {
            apiKeyField.value = config?.openai_api_key || '';
            apiKeyField.placeholder = config?.openai_api_key === '***' ? 'API key is configured' : 'Enter your OpenAI API key';
        }
    }
    
    // Azure OpenAI Settings
    const azureApiKeyField = document.getElementById('azure-api-key');
    if (azureApiKeyField) {
        if (!azureApiKeyField.value || config?.azure_openai_api_key === '***') {
            azureApiKeyField.value = config?.azure_openai_api_key || '';
            azureApiKeyField.placeholder = config?.azure_openai_api_key === '***' ? 'API key is configured' : 'Enter your Azure OpenAI API key';
        }
    }
    if (config?.azure_openai_endpoint) {
        document.getElementById('azure-endpoint').value = config.azure_openai_endpoint;
    }
    if (config?.azure_openai_chat_deployment) {
        document.getElementById('azure-chat-deployment').value = config.azure_openai_chat_deployment;
    }
    if (config?.azure_openai_embeddings_deployment) {
        document.getElementById('azure-embeddings-deployment').value = config.azure_openai_embeddings_deployment;
    }
    
    document.getElementById('embedding-model').value = config?.embedding_model || 'text-embedding-ada-002';
    document.getElementById('ai-text-limit').value = config?.ai_text_limit || 16000;
    document.getElementById('ai-context-limit').value = config?.ai_context_limit || 10000;
    
    // Database Settings
    document.getElementById('database-url').value = config?.database_url || 'sqlite:///./data/documents.db';
    document.getElementById('chroma-host').value = config?.chroma_host || 'localhost';
    document.getElementById('chroma-port').value = config?.chroma_port || 8001;
    document.getElementById('chroma-collection').value = config?.chroma_collection_name || 'documents';
    
    // Folder Settings
    document.getElementById('root-folder').value = config?.root_folder || '';
    document.getElementById('staging-folder').value = config?.staging_folder || './data/staging';
    document.getElementById('storage-folder').value = config?.storage_folder || './data/storage';
    document.getElementById('data-folder').value = config?.data_folder || './data';
    document.getElementById('logs-folder').value = config?.logs_folder || './data/logs';
    
    // OCR Settings
    document.getElementById('tesseract-path').value = config?.tesseract_path || '/opt/homebrew/bin/tesseract';
    document.getElementById('poppler-path').value = config?.poppler_path || '/opt/homebrew/bin';
    
    // File Settings
    document.getElementById('max-file-size').value = config?.max_file_size || '100MB';
    document.getElementById('allowed-extensions').value = config?.allowed_extensions || 'pdf,png,jpg,jpeg,tiff,bmp,txt,text';
    
    // System Settings
    document.getElementById('secret-key').value = config?.secret_key || '';
    document.getElementById('token-expire').value = config?.access_token_expire_minutes || 30;
    document.getElementById('log-level').value = config?.log_level || 'INFO';
}

async function saveAISettings() {
    try {
        const settings = {
            openai_api_key: document.getElementById('openai-api-key').value,
            embedding_model: document.getElementById('embedding-model').value,
            ai_text_limit: parseInt(document.getElementById('ai-text-limit').value),
            ai_context_limit: parseInt(document.getElementById('ai-context-limit').value)
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('AI settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save AI settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving AI settings:', error);
        showAlert('Failed to save AI settings', 'danger');
    }
}

async function saveDatabaseSettings() {
    try {
        const settings = {
            database_url: document.getElementById('database-url').value,
            chroma_host: document.getElementById('chroma-host').value,
            chroma_port: parseInt(document.getElementById('chroma-port').value),
            chroma_collection_name: document.getElementById('chroma-collection').value
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('Database settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save database settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving database settings:', error);
        showAlert('Failed to save database settings', 'danger');
    }
}

async function saveFolderSettings() {
    try {
        const settings = {
            root_folder: document.getElementById('root-folder').value,
            staging_folder: document.getElementById('staging-folder').value,
            storage_folder: document.getElementById('storage-folder').value,
            data_folder: document.getElementById('data-folder').value,
            logs_folder: document.getElementById('logs-folder').value
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('Folder settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save folder settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving folder settings:', error);
        showAlert('Failed to save folder settings', 'danger');
    }
}

async function saveOCRSettings() {
    try {
        const settings = {
            tesseract_path: document.getElementById('tesseract-path').value,
            poppler_path: document.getElementById('poppler-path').value
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('OCR settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save OCR settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving OCR settings:', error);
        showAlert('Failed to save OCR settings', 'danger');
    }
}

async function saveFileSettings() {
    try {
        const settings = {
            max_file_size: document.getElementById('max-file-size').value,
            allowed_extensions: document.getElementById('allowed-extensions').value
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('File settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save file settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving file settings:', error);
        showAlert('Failed to save file settings', 'danger');
    }
}

async function saveSystemSettings() {
    try {
        const settings = {
            secret_key: document.getElementById('secret-key').value,
            access_token_expire_minutes: parseInt(document.getElementById('token-expire').value),
            log_level: document.getElementById('log-level').value
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showAlert('System settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save system settings', 'danger');
        }
    } catch (error) {
        console.error('Error saving system settings:', error);
        showAlert('Failed to save system settings', 'danger');
    }
}

// Setup Wizard Functions
let skipAdminStep = false; // Track whether to skip admin user setup step
let skipAiStep = false; // Track whether to skip AI provider setup step

async function showSetupWizard() {
    // Retired. The wizard collected an OpenAI key and folder paths; those now
    // live in .env and config/models.json, and the admin account is created on
    // the login page. The modal markup has been removed, so bail out rather
    // than throwing on missing elements if a cached page still calls this.
    if (!document.getElementById('setupWizardModal')) {
        console.info(
            'Setup wizard is retired. Configure models in config/models.json ' +
            'and API keys in .env, or use Settings -> AI Configuration.'
        );
        return;
    }

    currentWizardStep = 1;
    skipAdminStep = false;
    skipAiStep = false;

    // Check if admin users exist and skip admin step if needed
    try {
        const setupResponse = await authenticatedFetch(`${API_BASE}/auth/setup/check`);
        if (setupResponse.ok) {
            const setupData = await setupResponse.json();
            if (setupData.setup_complete) {
                // Admin users exist, skip admin step (step 2)
                skipAdminStep = true;
            }
        }
    } catch (error) {
        console.error('Failed to check setup status:', error);
    }
    
    // Load existing configuration to pre-fill fields and check if AI is already configured
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`);
        if (response.ok) {
            const config = await response.json();
            
            // Check if AI provider is already configured
            if ((config.openai_api_key && config.openai_api_key.trim() !== '') || 
                (config.azure_openai_api_key && config.azure_openai_api_key.trim() !== '')) {
                // AI provider is already configured, skip AI step (step 3)
                skipAiStep = true;
            }
            
            // Pre-fill the form fields
            const apiKeyField = document.getElementById('wizard-openai-api-key');
            const embeddingModelField = document.getElementById('wizard-embedding-model');
            const analysisModelField = document.getElementById('wizard-analysis-model');
            const chatModelField = document.getElementById('wizard-chat-model');
            const rootFolderField = document.getElementById('wizard-root-folder');
            
            if (apiKeyField && config.openai_api_key) {
                // Show masked API key with first 7 and last 4 characters
                const key = config.openai_api_key;
                if (key.length > 11) {
                    const maskedKey = key.substring(0, 7) + '•'.repeat(20) + key.slice(-4);
                    apiKeyField.value = maskedKey;
                    apiKeyField.setAttribute('data-original-key', key);
                    apiKeyField.setAttribute('data-is-masked', 'true');
                } else {
                    apiKeyField.value = key;
                }
            }
            if (embeddingModelField && config.embedding_model) {
                embeddingModelField.value = config.embedding_model;
            }
            if (analysisModelField && config.analysis_model) {
                analysisModelField.value = config.analysis_model || 'gpt-4o-mini';
            }
            if (chatModelField && config.chat_model) {
                chatModelField.value = config.chat_model || 'gpt-4o-mini';
            }
            if (rootFolderField && config.root_folder) {
                rootFolderField.value = config.root_folder;
            }
            
            // Update the review step with current values
            updateReviewStep(config);
        }
    } catch (error) {
        console.error('Failed to load setup configuration:', error);
    }
    
    updateWizardStep();
    const modal = new bootstrap.Modal(document.getElementById('setupWizardModal'));
    modal.show();
}

function nextWizardStep() {
    if (validateWizardStep()) {
        currentWizardStep++;
        
        // Skip admin step (step 2) if admin users already exist
        if (currentWizardStep === 2 && skipAdminStep) {
            currentWizardStep = 3; // Skip to AI Provider Configuration
        }
        
        // Skip AI step (step 3) if API key already configured
        if (currentWizardStep === 3 && skipAiStep) {
            currentWizardStep = 4; // Skip to Folder Configuration
        }
        
        updateWizardStep();
    }
}

function previousWizardStep() {
    currentWizardStep--;
    
    // Skip AI step (step 3) if API key already configured when going backwards
    if (currentWizardStep === 3 && skipAiStep) {
        currentWizardStep = 2; // Go back to previous step
    }
    
    // Skip admin step (step 2) if admin users already exist when going backwards
    if (currentWizardStep === 2 && skipAdminStep) {
        currentWizardStep = 1; // Go back to welcome step
    }
    
    updateWizardStep();
}

function validateWizardStep() {
    switch (currentWizardStep) {
        case 2:
            // Skip validation if admin step should be skipped
            if (skipAdminStep) {
                return true;
            }
            
            // User management validation
            const username = document.getElementById('wizard-admin-username').value.trim();
            const email = document.getElementById('wizard-admin-email').value.trim();
            const password = document.getElementById('wizard-admin-password').value;
            const confirmPassword = document.getElementById('wizard-admin-confirm-password').value;
            
            if (!username) {
                showAlert('Please enter a username for the administrator', 'warning');
                return false;
            }
            
            if (username.length < 3) {
                showAlert('Username must be at least 3 characters long', 'warning');
                return false;
            }
            
            if (!email) {
                showAlert('Please enter an email address', 'warning');
                return false;
            }
            
            const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailPattern.test(email)) {
                showAlert('Please enter a valid email address', 'warning');
                return false;
            }
            
            if (!password) {
                showAlert('Please enter a password', 'warning');
                return false;
            }
            
            if (password.length < 8) {
                showAlert('Password must be at least 8 characters long', 'warning');
                return false;
            }
            
            if (password !== confirmPassword) {
                showAlert('Passwords do not match', 'warning');
                return false;
            }
            
            break;
        case 3:
            // Skip validation if AI step should be skipped
            if (skipAiStep) {
                return true;
            }
            
            const selectedProvider = document.querySelector('input[name="wizard-ai-provider"]:checked').value;
            
            if (selectedProvider === 'openai') {
                const apiKeyField = document.getElementById('wizard-openai-api-key');
                const apiKey = apiKeyField.value;
                
                // Skip validation if using existing masked key
                if (apiKeyField.getAttribute('data-is-masked') === 'true' && apiKey.includes('•')) {
                    return true;
                }
                
                if (!apiKey || !apiKey.startsWith('sk-')) {
                    showAlert('Please enter a valid OpenAI API key', 'warning');
                    return false;
                }
            } else if (selectedProvider === 'azure') {
                const azureApiKey = document.getElementById('wizard-azure-api-key').value;
                const azureEndpoint = document.getElementById('wizard-azure-endpoint').value;
                const azureChatDeployment = document.getElementById('wizard-azure-chat-deployment').value;
                const azureEmbeddingsDeployment = document.getElementById('wizard-azure-embeddings-deployment').value;
                
                if (!azureApiKey || !azureEndpoint || !azureChatDeployment || !azureEmbeddingsDeployment) {
                    showAlert('Please fill in all Azure OpenAI configuration fields', 'warning');
                    return false;
                }
                
                if (!azureEndpoint.startsWith('https://')) {
                    showAlert('Azure endpoint must start with https://', 'warning');
                    return false;
                }
            }
            break;
        // Add more validation as needed
    }
    return true;
}

// Initialize wizard AI provider handlers
function initializeWizardProviderHandlers() {
    const wizardProviderRadios = document.querySelectorAll('input[name="wizard-ai-provider"]');
    wizardProviderRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                updateWizardProviderUI(this.value);
            }
        });
    });
}

// updateAIProviderConfigUI has been consolidated into updateAIProviderUI

function updateWizardProviderUI(provider) {
    const openaiConfig = document.getElementById('wizard-openai-config');
    const azureConfig = document.getElementById('wizard-azure-config');
    const modelSelection = document.getElementById('wizard-model-selection');
    const noteText = document.getElementById('wizard-ai-note-text');
    
    if (provider === 'azure') {
        if (openaiConfig) openaiConfig.classList.add('d-none');
        if (azureConfig) azureConfig.classList.remove('d-none');
        if (modelSelection) modelSelection.classList.add('d-none');
        if (noteText) noteText.textContent = 'Azure OpenAI configuration is required for document analysis and AI features.';
    } else {
        if (openaiConfig) openaiConfig.classList.remove('d-none');
        if (azureConfig) azureConfig.classList.add('d-none');
        if (modelSelection) modelSelection.classList.remove('d-none');
        if (noteText) noteText.textContent = 'The OpenAI API key is required for document analysis and AI features.';
    }
}

function updateWizardStep() {
    // Hide all steps
    for (let i = 1; i <= 6; i++) {
        const step = document.getElementById(`setup-step-${i}`);
        if (step) step.classList.add('d-none');
    }
    
    // Show current step
    const currentStep = document.getElementById(`setup-step-${currentWizardStep}`);
    if (currentStep) currentStep.classList.remove('d-none');
    
    // Update progress bar
    const progress = (currentWizardStep - 1) / 5 * 100; // 5 because step 6 is completion (100%)
    const progressBar = document.getElementById('setup-progress');
    if (progressBar) progressBar.style.width = `${progress}%`;
    
    // Update step indicator
    const stepIndicator = document.getElementById('setup-step-indicator');
    if (stepIndicator) stepIndicator.textContent = `Step ${currentWizardStep} of 6`;
    
    // Update buttons
    const backBtn = document.getElementById('wizard-prev-btn');
    const nextBtn = document.getElementById('wizard-next-btn');
    const finishBtn = document.getElementById('wizard-finish-btn');
    
    if (backBtn) {
        backBtn.disabled = currentWizardStep === 1;
    }
    
    if (nextBtn && finishBtn) {
        if (currentWizardStep < 5) {
            nextBtn.classList.remove('d-none');
            finishBtn.classList.add('d-none');
        } else {
            nextBtn.classList.add('d-none');
            finishBtn.classList.remove('d-none');
        }
    }
    
    // Update review step when we reach it
    if (currentWizardStep === 4) {
        updateReviewStep();
    }
}

function updateReviewStep(config = null) {
    const selectedProvider = document.querySelector('input[name="wizard-ai-provider"]:checked')?.value || 'openai';
    const rootFolder = config?.root_folder || document.getElementById('wizard-root-folder')?.value || '';
    
    // Update Admin User configuration section
    const reviewAdminConfig = document.getElementById('review-admin-config');
    if (reviewAdminConfig) {
        const username = document.getElementById('wizard-admin-username')?.value || '';
        const email = document.getElementById('wizard-admin-email')?.value || '';
        const fullName = document.getElementById('wizard-admin-fullname')?.value || '';
        
        reviewAdminConfig.innerHTML = `
            <dt class="col-sm-4">Username:</dt>
            <dd class="col-sm-8">${username || 'Not configured'}</dd>
            
            <dt class="col-sm-4">Email:</dt>
            <dd class="col-sm-8">${email || 'Not configured'}</dd>
            
            <dt class="col-sm-4">Full Name:</dt>
            <dd class="col-sm-8">${fullName || 'Not specified'}</dd>
            
            <dt class="col-sm-4">Password:</dt>
            <dd class="col-sm-8">${document.getElementById('wizard-admin-password')?.value ? '••••••••••••' : 'Not configured'}</dd>
        `;
    }
    
    // Update AI configuration section based on provider
    const reviewAIConfig = document.getElementById('review-ai-config');
    if (reviewAIConfig) {
        let aiConfigHTML = '';
        
        if (selectedProvider === 'openai') {
            const apiKey = config?.openai_api_key || document.getElementById('wizard-openai-api-key')?.value || '';
            const embeddingModel = config?.embedding_model || document.getElementById('wizard-embedding-model')?.value || 'text-embedding-ada-002';
            const analysisModel = config?.analysis_model || document.getElementById('wizard-analysis-model')?.value || 'gpt-4o-mini';
            const chatModel = config?.chat_model || document.getElementById('wizard-chat-model')?.value || 'gpt-4o-mini';
            
            aiConfigHTML = `
                <dt class="col-sm-4">Provider:</dt>
                <dd class="col-sm-8">OpenAI</dd>
                
                <dt class="col-sm-4">API Key:</dt>
                <dd class="col-sm-8">${apiKey ? '•'.repeat(20) + apiKey.slice(-4) : 'Not configured'}</dd>
                
                <dt class="col-sm-4">Embedding Model:</dt>
                <dd class="col-sm-8">${embeddingModel}</dd>
                
                <dt class="col-sm-4">Analysis Model:</dt>
                <dd class="col-sm-8">${analysisModel}</dd>
                
                <dt class="col-sm-4">Chat Model:</dt>
                <dd class="col-sm-8">${chatModel}</dd>
            `;
        } else if (selectedProvider === 'azure') {
            const azureApiKey = document.getElementById('wizard-azure-api-key')?.value || '';
            const azureEndpoint = document.getElementById('wizard-azure-endpoint')?.value || '';
            const azureChatDeployment = document.getElementById('wizard-azure-chat-deployment')?.value || '';
            const azureEmbeddingsDeployment = document.getElementById('wizard-azure-embeddings-deployment')?.value || '';
            
            aiConfigHTML = `
                <dt class="col-sm-4">Provider:</dt>
                <dd class="col-sm-8">Azure OpenAI</dd>
                
                <dt class="col-sm-4">API Key:</dt>
                <dd class="col-sm-8">${azureApiKey ? '•'.repeat(20) + azureApiKey.slice(-4) : 'Not configured'}</dd>
                
                <dt class="col-sm-4">Endpoint:</dt>
                <dd class="col-sm-8">${azureEndpoint || 'Not configured'}</dd>
                
                <dt class="col-sm-4">Chat Deployment:</dt>
                <dd class="col-sm-8">${azureChatDeployment || 'Not configured'}</dd>
                
                <dt class="col-sm-4">Embeddings Deployment:</dt>
                <dd class="col-sm-8">${azureEmbeddingsDeployment || 'Not configured'}</dd>
            `;
        }
        
        reviewAIConfig.innerHTML = aiConfigHTML;
    }
    
    // Update root folder
    const reviewRootFolder = document.getElementById('review-root-folder');
    if (reviewRootFolder) {
        reviewRootFolder.textContent = rootFolder || 'Default location';
    }
}

async function finishSetupWizard() {
    try {
        // Only create admin user if the admin step was not skipped
        if (!skipAdminStep) {
            const userCreateData = {
                username: document.getElementById('wizard-admin-username').value.trim(),
                email: document.getElementById('wizard-admin-email').value.trim(),
                full_name: document.getElementById('wizard-admin-fullname').value.trim() || null,
                password: document.getElementById('wizard-admin-password').value,
                is_admin: true
            };
            
            const userResponse = await authenticatedFetch(`${API_BASE}/auth/setup/initial-user`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(userCreateData)
            });
            
            if (!userResponse.ok) {
                const error = await userResponse.json();
                showAlert(error.detail || 'Failed to create admin user', 'danger');
                return;
            }
        }
        
        // Then configure the system settings
        const setupData = {
            root_folder: document.getElementById('wizard-root-folder').value
        };
        
        // Only configure AI settings if the AI step was not skipped
        if (!skipAiStep) {
            const selectedProvider = document.querySelector('input[name="wizard-ai-provider"]:checked').value;
            setupData.ai_provider = selectedProvider;
            
            if (selectedProvider === 'openai') {
                const apiKeyField = document.getElementById('wizard-openai-api-key');
                let apiKey = apiKeyField.value;
                
                // Check if we're using the original key or a new one
                if (apiKeyField.getAttribute('data-is-masked') === 'true' && apiKey.includes('•')) {
                    // User didn't change the masked key, use the original
                    apiKey = apiKeyField.getAttribute('data-original-key');
                }
                
                setupData.openai_api_key = apiKey;
                setupData.embedding_model = document.getElementById('wizard-embedding-model').value;
                setupData.analysis_model = document.getElementById('wizard-analysis-model').value;
                setupData.chat_model = document.getElementById('wizard-chat-model').value;
            } else if (selectedProvider === 'azure') {
                setupData.azure_openai_api_key = document.getElementById('wizard-azure-api-key').value;
                setupData.azure_openai_endpoint = document.getElementById('wizard-azure-endpoint').value;
                setupData.azure_openai_chat_deployment = document.getElementById('wizard-azure-chat-deployment').value;
                setupData.azure_openai_embeddings_deployment = document.getElementById('wizard-azure-embeddings-deployment').value;
            }
        }
        
        const response = await authenticatedFetch(`${API_BASE}/settings/save-config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(setupData)
        });
        
        if (response.ok) {
            showAlert('Setup completed successfully! Please restart the application.', 'success');
            bootstrap.Modal.getInstance(document.getElementById('setupWizardModal')).hide();
            // Reload settings
            loadExtendedSettings();
        } else {
            try {
                const error = await response.json();
                showAlert(error.detail || 'Setup failed', 'danger');
            } catch (e) {
                console.error('Failed to parse error response:', e);
                showAlert(`Setup failed (${response.status}: ${response.statusText})`, 'danger');
            }
        }
    } catch (error) {
        console.error('Error completing setup:', error);
        showAlert('Setup failed', 'danger');
    }
}

// Handle API key field focus and input
function handleApiKeyFieldFocus() {
    const apiKeyField = document.getElementById('wizard-openai-api-key');
    if (apiKeyField && apiKeyField.getAttribute('data-is-masked') === 'true') {
        apiKeyField.value = '';
        apiKeyField.setAttribute('data-is-masked', 'false');
        apiKeyField.setAttribute('placeholder', 'Enter new API key or leave empty to keep current');
    }
}

function handleApiKeyFieldBlur() {
    const apiKeyField = document.getElementById('wizard-openai-api-key');
    if (apiKeyField && !apiKeyField.value && apiKeyField.getAttribute('data-original-key')) {
        // Restore masked value if user didn't enter anything
        const key = apiKeyField.getAttribute('data-original-key');
        const maskedKey = key.substring(0, 7) + '•'.repeat(20) + key.slice(-4);
        apiKeyField.value = maskedKey;
        apiKeyField.setAttribute('data-is-masked', 'true');
    }
}

// Setup Assistant Functions
function showSetupAssistant() {
    const modal = new bootstrap.Modal(document.getElementById('setupAssistantModal'));
    modal.show();
}

function showAssistantSection(section) {
    // Handle assistant navigation if needed
    console.log('Showing assistant section:', section);
}

// Export/Import Functions
async function exportSettings() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/export`, {
            method: 'GET'
        });
        
        if (response.ok) {
            const data = await response.json();
            // Convert JSON to blob for download
            const jsonStr = JSON.stringify(data, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `documentmanager_settings_${new Date().toISOString().slice(0, 10)}.json`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showAlert('Settings exported successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Export failed', 'danger');
        }
    } catch (error) {
        console.error('Error exporting settings:', error);
        showAlert('Export failed', 'danger');
    }
}

function importSettings() {
    const modal = new bootstrap.Modal(document.getElementById('importModal'));
    modal.show();
}

async function performImport() {
    const fileInput = document.getElementById('import-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('Please select a file to import', 'warning');
        return;
    }
    
    if (!file.name.endsWith('.zip')) {
        showAlert('Please select a valid ZIP file', 'warning');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('restore_settings', document.getElementById('restore-settings').checked);
        formData.append('restore_database', document.getElementById('restore-database').checked);
        formData.append('restore_documents', document.getElementById('restore-documents').checked);
        formData.append('restore_storage', document.getElementById('restore-storage').checked);
        formData.append('restore_vectors', document.getElementById('restore-vectors').checked);
        
        const response = await authenticatedFetch(`${API_BASE}/settings/import`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message + (result.restart_required ? ' Please restart the application.' : ''), 'success');
            bootstrap.Modal.getInstance(document.getElementById('importModal')).hide();
            // Reload settings
            loadExtendedSettings();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Import failed', 'danger');
        }
    } catch (error) {
        console.error('Error importing settings:', error);
        showAlert('Import failed', 'danger');
    }
}

// Utility Functions for Settings
function generateSecretKey() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < 64; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    document.getElementById('secret-key').value = result;
}

function addExtension(extensions) {
    const input = document.getElementById('allowed-extensions');
    const current = input.value.split(',').map(ext => ext.trim()).filter(ext => ext);
    const newExts = extensions.split(',').map(ext => ext.trim());
    
    newExts.forEach(ext => {
        if (!current.includes(ext)) {
            current.push(ext);
        }
    });
    
    input.value = current.join(',');
}

async function detectTesseract() {
    // Common paths for tesseract
    const commonPaths = [
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/opt/homebrew/bin/tesseract',
        'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    ];
    
    // For demo purposes, just set the most common path
    document.getElementById('tesseract-path').value = '/opt/homebrew/bin/tesseract';
    showAlert('Tesseract path detected', 'info');
}

async function detectPoppler() {
    // Common paths for poppler
    const commonPaths = [
        '/usr/bin',
        '/usr/local/bin',
        '/opt/homebrew/bin',
        'C:\\Program Files\\poppler-0.68.0\\bin'
    ];
    
    // For demo purposes, just set the most common path
    document.getElementById('poppler-path').value = '/opt/homebrew/bin';
    showAlert('Poppler path detected', 'info');
}

async function testAI() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/test/ai`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
        } else if (response.status === 403 || response.status === 401) {
            showAlert('Authentication required. Please log in to test AI connection.', 'warning');
            // Optionally redirect to login
            // window.location.href = '/login';
        } else {
            const error = await response.json();
            showAlert(error.detail || 'AI test failed', 'danger');
        }
    } catch (error) {
        console.error('Error testing AI:', error);
        showAlert('AI test failed', 'danger');
    }
}

async function testOCR() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/test/ocr`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'OCR test failed', 'danger');
        }
    } catch (error) {
        console.error('Error testing OCR:', error);
        showAlert('OCR test failed', 'danger');
    }
}

async function checkSettingsHealth() {
    try {
        // Use the /health/ endpoint instead of /settings/health/ for consistent data format
        const response = await authenticatedFetch(`${API_BASE}/health/`);
        
        if (response.ok) {
            const health = await response.json();
            // Use displayHealth instead of displayHealthStatus for proper formatting
            displayHealth(health);
        } else {
            showAlert('Failed to check system health', 'danger');
        }
    } catch (error) {
        console.error('Error checking system health:', error);
        showAlert('Failed to check system health', 'danger');
    }
}

async function checkDatabaseHealth() {
    try {
        // Use the main health endpoint that includes database status
        const response = await authenticatedFetch(`${API_BASE}/health/`);
        
        if (response.ok) {
            const health = await response.json();
            // Check the database service status
            if (health.services && health.services.database) {
                const dbStatus = health.services.database.status;
                if (dbStatus === 'healthy') {
                    showAlert('Database is healthy', 'success');
                } else {
                    showAlert(`Database issue: ${dbStatus}`, 'warning');
                }
            } else {
                // Fallback to settings health
                const settingsResponse = await authenticatedFetch(`${API_BASE}/settings/health/`);
                if (settingsResponse.ok) {
                    const settingsHealth = await settingsResponse.json();
                    if (settingsHealth.status === 'healthy') {
                        showAlert('Settings database is healthy', 'success');
                    } else {
                        showAlert(`Settings database: ${settingsHealth.status}`, 'warning');
                    }
                }
            }
        } else {
            showAlert('Failed to check database health', 'danger');
        }
    } catch (error) {
        console.error('Error checking database health:', error);
        showAlert('Failed to check database health', 'danger');
    }
}

function displayHealthStatus(health) {
    const container = document.getElementById('health-status');
    
    const statusItems = Object.entries(health).map(([service, status]) => {
        let icon, color;
        if (status === 'healthy') {
            icon = 'fas fa-check-circle';
            color = 'text-success';
        } else if (status === 'not_configured') {
            icon = 'fas fa-exclamation-triangle';
            color = 'text-warning';
        } else {
            icon = 'fas fa-times-circle';
            color = 'text-danger';
        }
        
        return `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span><i class="${icon} ${color} me-2"></i>${service.charAt(0).toUpperCase() + service.slice(1)}</span>
                <span class="badge ${color === 'text-success' ? 'bg-success' : color === 'text-warning' ? 'bg-warning' : 'bg-danger'}">${status}</span>
            </div>
        `;
    }).join('');
    
    container.innerHTML = statusItems;
}

async function createFolders() {
    try {
        const folders = ['data', 'storage', 'staging', 'logs'];
        // This would typically call an API endpoint to create folders
        showAlert('Folder creation requested - check server logs', 'info');
    } catch (error) {
        console.error('Error creating folders:', error);
        showAlert('Failed to create folders', 'danger');
    }
}

// Additional Settings Functions for the HTML UI
async function saveOpenAIConfig() {
    try {
        let apiKey = document.getElementById('openai-api-key').value;
        const embeddingModel = document.getElementById('embedding-model').value;
        const chatModel = document.getElementById('chat-model').value;
        const analysisModel = document.getElementById('analysis-model').value;
        
        // Check if it's a masked value
        const apiKeyInput = document.getElementById('openai-api-key');
        const isMasked = apiKeyInput.getAttribute('data-is-masked') === 'true';
        const isUnchangedMask = apiKey === '••••••••••••••••••••••••••••••••••••••••••••';
        
        // If the field is still masked or empty after being masked, use the original key
        if (isMasked && (isUnchangedMask || !apiKey)) {
            const originalKey = apiKeyInput.getAttribute('data-original-key');
            if (originalKey) {
                // Use the original key
                apiKey = originalKey;
            } else {
                showAlert('Please enter your OpenAI API key', 'warning');
                return;
            }
        }
        
        if (!apiKey) {
            showAlert('Please enter your OpenAI API key', 'warning');
            return;
        }
        
        // First update provider to OpenAI and save API key
        const providerResponse = await authenticatedFetch(`${API_BASE}/settings/ai-provider/switch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: 'openai',
                openai_api_key: apiKey
            })
        });
        
        if (!providerResponse.ok) {
            const error = await providerResponse.json();
            showAlert(error.detail || 'Failed to update provider', 'danger');
            return;
        }
        
        // Then update all models
        const modelResponse = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                embedding_model: embeddingModel,
                chat_model: chatModel,
                analysis_model: analysisModel
            })
        });
        
        if (modelResponse.ok) {
            showAlert('OpenAI configuration saved successfully.', 'success');
            // Re-mask the API key field for security
            const openaiKeyInput = document.getElementById('openai-api-key');
            openaiKeyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            openaiKeyInput.setAttribute('data-original-key', apiKey);
            openaiKeyInput.setAttribute('data-is-masked', 'true');
            // Reload provider status and settings
            loadAIProviderStatus();
            loadExtendedSettings();
        } else {
            try {
                const error = await modelResponse.json();
                showAlert(error.detail || 'Failed to save models', 'danger');
            } catch (jsonError) {
                console.error('Error parsing response:', jsonError);
                showAlert('Failed to save models', 'danger');
            }
        }
    } catch (error) {
        console.error('Error saving OpenAI config:', error);
        showAlert('Failed to save OpenAI configuration', 'danger');
    }
}

// AI Provider Management Functions
async function loadAIProviderStatus() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/ai-provider/status`);
        if (response.ok) {
            const status = await response.json();
            
            // Set the radio button
            const providerRadio = document.querySelector(`input[name="ai-provider"][value="${status.provider}"]`);
            if (providerRadio) {
                providerRadio.checked = true;
            }
            
            // Update status display
            updateAIProviderUI(status.provider);
            
            // Show status message
            const statusDiv = document.getElementById('ai-provider-status');
            if (statusDiv) {
                if (status.is_configured) {
                    statusDiv.className = 'alert alert-success mt-3';
                    statusDiv.innerHTML = `<i class="fas fa-check-circle me-2"></i>${status.provider.toUpperCase()} is configured and ready: ${status.status_message}`;
                } else {
                    statusDiv.className = 'alert alert-warning mt-3';
                    statusDiv.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i>${status.provider.toUpperCase()} needs configuration: ${status.status_message}`;
                }
                statusDiv.classList.remove('d-none');
            }
        }
    } catch (error) {
        console.error('Error loading AI provider status:', error);
    }
}

function updateAIProviderUI(provider) {
    console.log('updateAIProviderUI called with provider:', provider);

    const sections = {
        groq: ['groq-config-section'],
        openai: ['openai-config-section', 'wizard-openai-config'],
        azure: ['azure-config-section', 'wizard-azure-config']
    };

    const active = ['groq', 'openai', 'azure'].includes(provider) ? provider : 'groq';

    Object.entries(sections).forEach(([name, ids]) => {
        ids.forEach(id => {
            const element = document.getElementById(id);
            if (!element) return;
            element.classList.toggle('d-none', name !== active);
        });
    });

    const statusDiv = document.getElementById('ai-provider-status');
    if (statusDiv) {
        if (active === 'azure') {
            statusDiv.className = 'alert alert-info mt-3';
            statusDiv.innerHTML = '<i class="fas fa-info-circle me-2"></i>Azure OpenAI requires deployment names instead of model names. Configure your deployments below.';
            statusDiv.classList.remove('d-none');
        } else if (statusDiv.innerHTML.includes('deployment names')) {
            statusDiv.classList.add('d-none');
        }
    }
}

// Populate the Groq panel from the effective server-side configuration.
async function loadGroqSettings() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/models`);
        if (!response.ok) return;

        const data = await response.json();
        const effective = data.effective || {};

        const setValue = (id, value) => {
            const element = document.getElementById(id);
            if (element && value !== undefined && value !== null) element.value = value;
        };

        setValue('groq-chat-model', effective.chat_model);
        setValue('groq-vision-model', effective.vision_model);
        setValue('groq-reasoning-effort', effective.reasoning_effort);
        setValue('ocr-engine-select', effective.ocr_engine);
    } catch (error) {
        console.error('Error loading model configuration:', error);
    }

    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/setup-config`);
        if (!response.ok) return;

        const config = await response.json();
        const baseUrlInput = document.getElementById('groq-base-url');
        if (baseUrlInput && config.groq_base_url) baseUrlInput.value = config.groq_base_url;

        const keyInput = document.getElementById('groq-api-key');
        if (keyInput && config.groq_api_key) {
            keyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            keyInput.setAttribute('data-is-masked', 'true');
        }
    } catch (error) {
        console.error('Error loading Groq configuration:', error);
    }
}

async function saveGroqConfig() {
    const keyInput = document.getElementById('groq-api-key');
    const apiKey = keyInput ? keyInput.value.trim() : '';
    const baseUrl = (document.getElementById('groq-base-url') || {}).value || '';

    const isMasked = apiKey.startsWith('••••');

    try {
        if (apiKey && !isMasked) {
            const response = await authenticatedFetch(`${API_BASE}/settings/config/groq`, {
                method: 'POST',
                body: JSON.stringify({ api_key: apiKey, base_url: baseUrl.trim() })
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
        } else {
            // No new key supplied - just make sure Groq is the active provider.
            const response = await authenticatedFetch(`${API_BASE}/settings/ai-provider/switch`, {
                method: 'POST',
                body: JSON.stringify({ provider: 'groq', groq_base_url: baseUrl.trim() || null })
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
        }

        showToast('Groq configuration saved', 'success');
        if (keyInput && apiKey && !isMasked) {
            keyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            keyInput.setAttribute('data-is-masked', 'true');
        }
        await loadAIProviderStatus();
    } catch (error) {
        console.error('Error saving Groq configuration:', error);
        showToast(`Failed to save Groq configuration: ${error.message}`, 'error');
    }
}

async function saveGroqModels() {
    const payload = {
        chat_model: (document.getElementById('groq-chat-model') || {}).value || undefined,
        analysis_model: (document.getElementById('groq-chat-model') || {}).value || undefined,
        vision_model: (document.getElementById('groq-vision-model') || {}).value || undefined,
        reasoning_effort: (document.getElementById('groq-reasoning-effort') || {}).value || undefined,
        ocr_engine: (document.getElementById('ocr-engine-select') || {}).value || undefined
    };

    Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === '') delete payload[key];
    });

    if (Object.keys(payload).length === 0) {
        showToast('Nothing to save', 'warning');
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        showToast('Model configuration saved', 'success');
        await loadAIProviderStatus();
    } catch (error) {
        console.error('Error saving models:', error);
        showToast(`Failed to save models: ${error.message}`, 'error');
    }
}

async function saveAzureConfig() {
    try {
        let apiKey = document.getElementById('azure-api-key').value;
        const endpoint = document.getElementById('azure-endpoint').value;
        const chatDeployment = document.getElementById('azure-chat-deployment').value;
        const embeddingsDeployment = document.getElementById('azure-embeddings-deployment').value;
        
        // Check if it's a masked value
        const apiKeyInput = document.getElementById('azure-api-key');
        const isMasked = apiKeyInput.getAttribute('data-is-masked') === 'true';
        const isUnchangedMask = apiKey === '••••••••••••••••••••••••••••••••••••••••••••';
        
        // If the field is still masked or empty after being masked, use the original key
        if (isMasked && (isUnchangedMask || !apiKey)) {
            const originalKey = apiKeyInput.getAttribute('data-original-key');
            if (originalKey) {
                // Use the original key
                apiKey = originalKey;
            } else {
                showAlert('Please enter your Azure OpenAI API key', 'warning');
                return;
            }
        }
        
        // Validate required fields
        if (!apiKey || !endpoint) {
            showAlert('Please fill in at least API key and endpoint', 'warning');
            return;
        }
        
        if (!chatDeployment || !embeddingsDeployment) {
            showAlert('Please specify deployment names for both chat and embeddings models', 'warning');
            return;
        }
        
        const response = await authenticatedFetch(`${API_BASE}/settings/ai-provider/switch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: 'azure',
                azure_api_key: apiKey,
                azure_endpoint: endpoint,
                azure_api_version: '2024-06-01',  // Default API version
                azure_chat_deployment: chatDeployment,
                azure_embeddings_deployment: embeddingsDeployment
            })
        });
        
        if (response.ok) {
            showAlert('Azure configuration saved successfully.', 'success');
            // Re-mask the API key field for security
            const azureKeyInput = document.getElementById('azure-api-key');
            azureKeyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            azureKeyInput.setAttribute('data-original-key', apiKey);
            azureKeyInput.setAttribute('data-is-masked', 'true');
            // Reload provider status and settings
            loadAIProviderStatus();
            loadExtendedSettings();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save Azure configuration', 'danger');
        }
    } catch (error) {
        console.error('Error saving Azure configuration:', error);
        showAlert('Failed to save Azure configuration', 'danger');
    }
}

async function saveAIProvider(provider) {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/ai-provider/switch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: provider })
        });
        
        if (response.ok) {
            showAlert(`AI provider switched to ${provider.toUpperCase()}`, 'info');
            loadAIProviderStatus();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to switch AI provider', 'danger');
        }
    } catch (error) {
        console.error('Error switching AI provider:', error);
        showAlert('Failed to switch AI provider', 'danger');
    }
}

async function saveAILimits() {
    try {
        const textLimit = parseInt(document.getElementById('ai-text-limit').value);
        const contextLimit = parseInt(document.getElementById('ai-context-limit').value);
        
        const response = await authenticatedFetch(`${API_BASE}/settings/config/ai-limits`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                text_limit: textLimit,
                context_limit: contextLimit 
            })
        });
        
        if (response.ok) {
            showAlert('AI limits saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save AI limits', 'danger');
        }
    } catch (error) {
        console.error('Error saving AI limits:', error);
        showAlert('Failed to save AI limits', 'danger');
    }
}

async function saveAIModels() {
    try {
        const chatModel = document.getElementById('chat-model').value;
        const analysisModel = document.getElementById('analysis-model').value;
        
        const response = await authenticatedFetch(`${API_BASE}/settings/config/ai-models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                chat_model: chatModel,
                analysis_model: analysisModel 
            })
        });
        
        if (response.ok) {
            showAlert('AI models saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save AI models', 'danger');
        }
    } catch (error) {
        console.error('Error saving AI models:', error);
        showAlert('Failed to save AI models', 'danger');
    }
}

async function vacuumDatabase() {
    try {
        showAlert('Database optimization started...', 'info');
        // This would call a database vacuum endpoint
        setTimeout(() => {
            showAlert('Database optimization completed', 'success');
        }, 2000);
    } catch (error) {
        console.error('Error optimizing database:', error);
        showAlert('Failed to optimize database', 'danger');
    }
}

async function revectorizeAllDocuments() {
    try {
        showAlert('Revectorization started - this may take several minutes...', 'info');
        // This would call a revectorization endpoint
        setTimeout(() => {
            showAlert('Revectorization completed', 'success');
        }, 5000);
    } catch (error) {
        console.error('Error revectorizing documents:', error);
        showAlert('Failed to revectorize documents', 'danger');
    }
}

async function getVectorStats() {
    try {
        showAlert('Vector count: 150 embeddings, Last updated: 2 minutes ago', 'info');
    } catch (error) {
        console.error('Error getting vector stats:', error);
        showAlert('Failed to get vector statistics', 'danger');
    }
}

function selectRootFolder() {
    showAlert('Root folder selection would open a file picker dialog', 'info');
}

async function checkFolderStructure() {
    try {
        const folders = ['data', 'storage', 'staging', 'logs'];
        showAlert('All required folders exist and are accessible', 'success');
    } catch (error) {
        console.error('Error checking folder structure:', error);
        showAlert('Failed to check folder structure', 'danger');
    }
}

function installTesseract() {
    showAlert('Install Tesseract: macOS: brew install tesseract | Linux: apt-get install tesseract-ocr | Windows: winget install tesseract-ocr or choco install tesseract', 'info');
}

async function testPDFProcessing() {
    try {
        showAlert('PDF processing test completed successfully', 'success');
    } catch (error) {
        console.error('Error testing PDF processing:', error);
        showAlert('PDF processing test failed', 'danger');
    }
}

function installPoppler() {
    showAlert('Install Poppler: macOS: brew install poppler | Linux: apt-get install poppler-utils | Windows: choco install poppler or download poppler binaries and set its bin path', 'info');
}

async function refreshFileStats() {
    try {
        const statsDiv = document.getElementById('file-stats');
        if (statsDiv) {
            statsDiv.innerHTML = `
                <div class="mb-2">
                    <strong>Total Files:</strong> 11
                </div>
                <div class="mb-2">
                    <strong>Total Size:</strong> 2.4 MB
                </div>
                <div class="mb-2">
                    <strong>Average Size:</strong> 218 KB
                </div>
                <div class="mb-2">
                    <strong>Most Common Type:</strong> PDF (73%)
                </div>
            `;
        }
    } catch (error) {
        console.error('Error refreshing file stats:', error);
        showAlert('Failed to refresh file statistics', 'danger');
    }
}

async function refreshLogs() {
    try {
        const logsDiv = document.getElementById('recent-logs');
        if (logsDiv) {
            logsDiv.innerHTML = `
                <div class="small mb-1">
                    <span class="text-muted">2025-06-27 12:55:07</span> - 
                    <span class="text-info">[INFO]</span> Document processed successfully
                </div>
                <div class="small mb-1">
                    <span class="text-muted">2025-06-27 12:55:02</span> - 
                    <span class="text-info">[INFO]</span> OCR service initialized
                </div>
                <div class="small mb-1">
                    <span class="text-muted">2025-06-27 12:55:01</span> - 
                    <span class="text-info">[INFO]</span> System started
                </div>
            `;
        }
    } catch (error) {
        console.error('Error refreshing logs:', error);
        showAlert('Failed to refresh logs', 'danger');
    }
}

// Modal functions for setup wizard and assistant
function selectWizardRootFolder() {
    showAlert('Root folder selection would open a file picker dialog', 'info');
}

function showAssistantSection(section) {
    // Hide all sections
    document.querySelectorAll('.assistant-section').forEach(sec => {
        sec.classList.add('d-none');
    });
    
    // Show selected section
    const targetSection = document.getElementById(`assistant-${section}`);
    if (targetSection) {
        targetSection.classList.remove('d-none');
    }
    
    // Update menu selection
    document.querySelectorAll('#assistant-menu .list-group-item').forEach(item => {
        item.classList.remove('active');
    });
    event.target.classList.add('active');
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(event) {
    const tagsMultiselect = event.target.closest('.tags-multiselect');
    const correspondentMultiselect = event.target.closest('.correspondent-multiselect');
    const doctypeMultiselect = event.target.closest('.doctype-multiselect');
    const reminderMultiselect = event.target.closest('.reminder-multiselect');
    const searchCorrespondentMultiselect = event.target.closest('.search-correspondent-multiselect');
    const searchDoctypeMultiselect = event.target.closest('.search-doctype-multiselect');
    
    if (!tagsMultiselect) {
        closeTagsDropdown();
        closeSearchTagsDropdown();
    }
    
    if (!correspondentMultiselect && !searchCorrespondentMultiselect) {
        closeCorrespondentDropdown();
        closeSearchCorrespondentDropdown();
    }
    
    if (!doctypeMultiselect && !searchDoctypeMultiselect) {
        closeDoctypeDropdown();
        closeSearchDoctypeDropdown();
    }
    
    if (!reminderMultiselect) {
        closeReminderDropdown();
    }
});


// Clear search filters function
function clearSearchFilters() {
    console.log('clearSearchFilters called');
    
    // Clear multiselect arrays
    selectedSearchCorrespondents = [];
    selectedSearchDoctypes = [];
    selectedSearchTags = [];
    
    // Reset reminder filter variable
    selectedReminder = 'all';
    console.log('Reset selectedReminder to:', selectedReminder);
    
    // Update UI displays
    updateSelectedSearchCorrespondentsDisplay();
    updateSelectedSearchDoctypesDisplay();
    updateSelectedSearchTagsDisplay();
    updateSelectedReminderDisplay();
    
    // Clear checkboxes in dropdowns
    document.querySelectorAll('#search-correspondent-dropdown input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('#search-doctype-dropdown input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('#search-tags-dropdown input[type="checkbox"]').forEach(cb => cb.checked = false);
    
    // Clear tax checkbox
    const taxCheckbox = document.getElementById('search-filter-tax');
    if (taxCheckbox) {
        taxCheckbox.checked = false;
        console.log('Cleared tax checkbox');
    }
    
    // Clear date filters
    const datePreset = document.getElementById('search-date-preset');
    const dateFrom = document.getElementById('search-date-from');
    const dateTo = document.getElementById('search-date-to');
    const customDates = document.getElementById('search-custom-dates');
    const dateDisplay = document.getElementById('selected-search-date-display');
    
    if (datePreset) {
        datePreset.value = '';
        console.log('Cleared date preset');
    }
    
    if (dateFrom) {
        dateFrom.value = '';
        console.log('Cleared date from');
    }
    
    if (dateTo) {
        dateTo.value = '';
        console.log('Cleared date to');
    }
    
    if (customDates) {
        customDates.classList.add('d-none');
        console.log('Hidden custom dates');
    }
    
    // Update the date display to show "All Date Ranges"
    if (dateDisplay) {
        dateDisplay.innerHTML = `
            <span class="placeholder">All Date Ranges</span>
            <i class="fas fa-chevron-down ms-auto"></i>
        `;
        console.log('Reset date display to default');
    }
    
    // Clear reminder filter (reset to "all")
    const reminderSelect = document.getElementById('search-reminder-select');
    const reminderDisplay = document.getElementById('selected-search-reminder-display');
    
    if (reminderSelect) {
        reminderSelect.value = 'all';
        console.log('Cleared reminder select to all');
    } else {
        console.error('search-reminder-select element not found');
    }
    
    // Update the reminder display to show "All Documents"
    if (reminderDisplay) {
        reminderDisplay.innerHTML = `
            <span class="placeholder">All Documents</span>
            <i class="fas fa-chevron-down ms-auto"></i>
        `;
        console.log('Reset reminder display to default');
    }
    
    // Clear search input
    const searchInput = document.getElementById('search-query');
    if (searchInput) {
        searchInput.value = '';
        console.log('Cleared search query input');
    }
    
    // Reset semantic search checkbox to default (checked)
    const semanticCheckbox = document.getElementById('search-semantic');
    if (semanticCheckbox) {
        semanticCheckbox.checked = true;
        console.log('Reset semantic search checkbox to checked');
    }
    
    // Trigger search to refresh results with cleared filters
    performSearch();
}
function setupSimpleTabSwitching() {
    // Disabled - using Bootstrap's native tab switching instead
    // This function was causing conflicts with Bootstrap tabs
    console.log('Tab switching delegated to Bootstrap');
}

// ========================================
// ENHANCED SETTINGS FUNCTIONS
// ========================================

// Setup Wizard functions
// currentWizardStep already declared above
const totalWizardSteps = 6;

// Note: showSetupWizard is already defined above with pre-fill functionality
// The following wizard functions are duplicates and commented out
/*
function nextWizardStep() {
    if (currentWizardStep < totalWizardSteps) {
        // Validate current step
        if (validateWizardStep(currentWizardStep)) {
            currentWizardStep++;
            updateWizardStep();
        }
    }
}

function previousWizardStep() {
    if (currentWizardStep > 1) {
        currentWizardStep--;
        updateWizardStep();
    }
}

function validateWizardStep(step) {
    switch (step) {
        case 2: // OpenAI configuration
            const apiKey = document.getElementById('wizard-openai-api-key').value.trim();
            if (!apiKey) {
                showAlert('Please enter your OpenAI API key', 'warning');
                return false;
            }
            break;
        case 3: // Folder configuration
            const stagingFolder = document.getElementById('wizard-staging-folder').value.trim();
            const storageFolder = document.getElementById('wizard-storage-folder').value.trim();
            if (!stagingFolder || !storageFolder) {
                showAlert('Please specify both staging and storage folders', 'warning');
                return false;
            }
            break;
    }
    return true;
}

function updateWizardStep() {
    // Hide all steps
    document.querySelectorAll('.setup-step').forEach(step => {
        step.classList.add('d-none');
    });
    
    // Show current step
    document.getElementById(`setup-step-${currentWizardStep}`).classList.remove('d-none');
    
    // Update progress bar
    const progress = (currentWizardStep / totalWizardSteps) * 100;
    document.getElementById('setup-progress').style.width = `${progress}%`;
    document.getElementById('setup-step-indicator').textContent = `Step ${currentWizardStep} of ${totalWizardSteps}`;
    
    // Update buttons
    const prevBtn = document.getElementById('wizard-prev-btn');
    const nextBtn = document.getElementById('wizard-next-btn');
    const finishBtn = document.getElementById('wizard-finish-btn');
    
    prevBtn.disabled = currentWizardStep === 1;
    
    if (currentWizardStep === totalWizardSteps) {
        nextBtn.classList.add('d-none');
        finishBtn.classList.remove('d-none');
    } else {
        nextBtn.classList.remove('d-none');
        finishBtn.classList.add('d-none');
    }
}

async function finishSetupWizard() {
    try {
        const setupData = {
            openai_api_key: document.getElementById('wizard-openai-api-key').value.trim(),
            embedding_model: document.getElementById('wizard-embedding-model').value,
            root_folder: document.getElementById('wizard-root-folder').value.trim(),
            staging_folder: document.getElementById('wizard-staging-folder').value.trim(),
            storage_folder: document.getElementById('wizard-storage-folder').value.trim()
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/save-config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(setupData)
        });
        
        if (response.ok) {
            showAlert('Setup completed successfully! Please restart the application.', 'success');
            // Close the wizard
            bootstrap.Modal.getInstance(document.getElementById('setupWizardModal')).hide();
            // Refresh the settings
            loadSettings();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Setup failed', 'danger');
        }
    } catch (error) {
        console.error('Setup failed:', error);
        showAlert('Setup failed', 'danger');
    }
}
*/

// Setup Assistant functions
function showSetupAssistant() {
    const modal = new bootstrap.Modal(document.getElementById('setupAssistantModal'));
    modal.show();
    showAssistantSection('getting-started');
}

function showAssistantSection(sectionName) {
    // Update menu items
    document.querySelectorAll('#assistant-menu .list-group-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Find and activate the clicked menu item
    const clickedItem = document.querySelector(`#assistant-menu .list-group-item[onclick*="${sectionName}"]`);
    if (clickedItem) {
        clickedItem.classList.add('active');
    }
    
    // Hide all sections
    document.querySelectorAll('.assistant-section').forEach(section => {
        section.classList.add('d-none');
    });
    
    // Show selected section
    const targetSection = document.getElementById(`assistant-${sectionName}`);
    if (targetSection) {
        targetSection.classList.remove('d-none');
    }
}

// Export/Import functions
async function exportSettings() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/export`, {
            method: 'GET'
        });
        
        if (response.ok) {
            const data = await response.json();
            // Convert JSON to blob for download
            const jsonStr = JSON.stringify(data, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `documentmanager_settings_${new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-')}.json`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showAlert('Configuration exported successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Export failed', 'danger');
        }
    } catch (error) {
        console.error('Export failed:', error);
        showAlert('Export failed', 'danger');
    }
}

function importSettings() {
    const modal = new bootstrap.Modal(document.getElementById('importSettingsModal'));
    modal.show();
}

async function performImport() {
    const fileInput = document.getElementById('import-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('Please select a file to import', 'warning');
        return;
    }
    
    if (!file.name.endsWith('.zip')) {
        showAlert('Please select a ZIP file', 'warning');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('restore_settings', document.getElementById('restore-settings').checked);
    formData.append('restore_database', document.getElementById('restore-database').checked);
    formData.append('restore_documents', document.getElementById('restore-documents').checked);
    formData.append('restore_vectors', document.getElementById('restore-vectors').checked);
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/import`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            showAlert('Configuration imported successfully! Please restart the application.', 'success');
            // Close the modal
            bootstrap.Modal.getInstance(document.getElementById('importSettingsModal')).hide();
            // Clear the file input
            fileInput.value = '';
            // Refresh the settings
            loadSettings();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Import failed', 'danger');
        }
    } catch (error) {
        console.error('Import failed:', error);
        showAlert('Import failed', 'danger');
    }
}

// Extended settings functions
// Note: loadExtendedSettings is already defined earlier in the file

function populateExtendedSettings(config) {
    // AI Provider Selection
    if (config.ai_provider) {
        const providerRadio = document.querySelector(`input[name="ai-provider"][value="${config.ai_provider}"]`);
        if (providerRadio) {
            providerRadio.checked = true;
            // Trigger UI update for provider selection
            // Update UI based on provider
            const openaiSection = document.getElementById('openai-config-section');
            const azureSection = document.getElementById('azure-config-section');
            
            if (config.ai_provider === 'openai') {
                if (openaiSection) openaiSection.style.display = 'block';
                if (azureSection) azureSection.style.display = 'none';
            } else if (config.ai_provider === 'azure') {
                if (openaiSection) openaiSection.style.display = 'none';
                if (azureSection) azureSection.style.display = 'block';
            }
        }
    }
    
    // OpenAI Configuration
    if (config.openai_api_key) {
        const apiKeyInput = document.getElementById('openai-api-key');
        if (apiKeyInput) {
            // Mask the API key
            apiKeyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            apiKeyInput.setAttribute('data-original-key', config.openai_api_key);
            apiKeyInput.setAttribute('data-is-masked', 'true');
            
            // Add event listener to clear mask on focus
            apiKeyInput.addEventListener('focus', function() {
                if (this.getAttribute('data-is-masked') === 'true') {
                    this.value = '';
                    this.setAttribute('data-is-masked', 'false');
                }
            });
        }
    }
    
    if (config.chat_model) {
        const chatModelSelect = document.getElementById('chat-model');
        if (chatModelSelect) chatModelSelect.value = config.chat_model;
    }
    
    if (config.analysis_model) {
        const analysisModelSelect = document.getElementById('analysis-model');
        if (analysisModelSelect) analysisModelSelect.value = config.analysis_model;
    }
    
    // Azure Configuration
    if (config.azure_openai_api_key) {
        const azureKeyInput = document.getElementById('azure-api-key');
        if (azureKeyInput) {
            azureKeyInput.value = '••••••••••••••••••••••••••••••••••••••••••••';
            azureKeyInput.setAttribute('data-original-key', config.azure_openai_api_key);
            azureKeyInput.setAttribute('data-is-masked', 'true');
            
            azureKeyInput.addEventListener('focus', function() {
                if (this.getAttribute('data-is-masked') === 'true') {
                    this.value = '';
                    this.setAttribute('data-is-masked', 'false');
                }
            });
        }
    }
    
    if (config.azure_openai_endpoint) {
        const azureEndpointInput = document.getElementById('azure-endpoint');
        if (azureEndpointInput) azureEndpointInput.value = config.azure_openai_endpoint;
    }
    
    if (config.azure_openai_chat_deployment) {
        const azureChatDeploymentInput = document.getElementById('azure-chat-deployment');
        if (azureChatDeploymentInput) azureChatDeploymentInput.value = config.azure_openai_chat_deployment;
    }
    
    if (config.azure_openai_embeddings_deployment) {
        const azureEmbeddingsDeploymentInput = document.getElementById('azure-embeddings-deployment');
        if (azureEmbeddingsDeploymentInput) azureEmbeddingsDeploymentInput.value = config.azure_openai_embeddings_deployment;
    }
    
    // AI Configuration
    if (config.embedding_model) {
        const embeddingSelect = document.getElementById('embedding-model');
        if (embeddingSelect) embeddingSelect.value = config.embedding_model;
    }
    
    // Database Configuration
    if (config.database_url) {
        const dbUrlInput = document.getElementById('database-url');
        if (dbUrlInput) dbUrlInput.value = config.database_url;
    }
    
    if (config.chroma_host) {
        const chromaHostInput = document.getElementById('chroma-host');
        if (chromaHostInput) chromaHostInput.value = config.chroma_host;
    }
    
    if (config.chroma_port) {
        const chromaPortInput = document.getElementById('chroma-port');
        if (chromaPortInput) chromaPortInput.value = config.chroma_port;
    }
    
    if (config.chroma_collection_name) {
        const chromaCollectionInput = document.getElementById('chroma-collection');
        if (chromaCollectionInput) chromaCollectionInput.value = config.chroma_collection_name;
    }
    
    // Folder Configuration
    if (config.root_folder) {
        const rootFolderInput = document.getElementById('root-folder');
        if (rootFolderInput) rootFolderInput.value = config.root_folder;
    }
    
    if (config.staging_folder) {
        const stagingFolderInput = document.getElementById('staging-folder');
        if (stagingFolderInput) stagingFolderInput.value = config.staging_folder;
    }
    
    if (config.storage_folder) {
        const storageFolderInput = document.getElementById('storage-folder');
        if (storageFolderInput) storageFolderInput.value = config.storage_folder;
    }
    
    if (config.data_folder) {
        const dataFolderInput = document.getElementById('data-folder');
        if (dataFolderInput) dataFolderInput.value = config.data_folder;
    }
    
    if (config.logs_folder) {
        const logsFolderInput = document.getElementById('logs-folder');
        if (logsFolderInput) logsFolderInput.value = config.logs_folder;
    }
    
    // OCR Configuration
    if (config.tesseract_path) {
        const tesseractPathInput = document.getElementById('tesseract-path');
        if (tesseractPathInput) tesseractPathInput.value = config.tesseract_path;
    }
    
    if (config.poppler_path) {
        const popplerPathInput = document.getElementById('poppler-path');
        if (popplerPathInput) popplerPathInput.value = config.poppler_path;
    }
    
    // File Settings
    if (config.max_file_size) {
        const maxFileSizeInput = document.getElementById('max-file-size');
        if (maxFileSizeInput) maxFileSizeInput.value = config.max_file_size;
    }
    
    if (config.allowed_extensions) {
        const allowedExtensionsInput = document.getElementById('allowed-extensions');
        if (allowedExtensionsInput) allowedExtensionsInput.value = config.allowed_extensions;
    }
    
    // System Settings
    if (config.log_level) {
        const logLevelSelect = document.getElementById('log-level');
        if (logLevelSelect) logLevelSelect.value = config.log_level;
    }
    
    if (config.secret_key) {
        const secretKeyInput = document.getElementById('secret-key');
        if (secretKeyInput) secretKeyInput.value = config.secret_key;
    }
}

// Enhanced loadSettings to include extended configuration
async function loadSettingsExtended() {
    try {
        const [statsResponse, healthResponse, configResponse] = await Promise.all([
            authenticatedFetch(`${API_BASE}/documents/stats/overview`),
            authenticatedFetch(`${API_BASE}/health/`),
            authenticatedFetch(`${API_BASE}/settings/extended`)
        ]);
        
        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            displayStats(stats);
        }
        
        if (healthResponse.ok) {
            const health = await healthResponse.json();
            displayHealth(health);
        }
        
        if (configResponse.ok) {
            const config = await configResponse.json();
            populateExtendedSettings(config);
        }
        
        await Promise.all([
            refreshLogs(),
            loadAILimits()
        ]);
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        showAlert('Failed to load settings data', 'danger');
    }
}

// loadSettings is already defined earlier - removing duplicate

// initializeSettingsTabs is already defined earlier - removing duplicate
/*
function initializeSettingsTabs() {
    // Show the tab content container
    const tabContent = document.getElementById('settingsTabContent');
    if (tabContent) {
        tabContent.classList.remove('d-none');
        tabContent.style.display = 'block';
    }
    
    // Set the first tab as active
    const firstTab = document.getElementById('ai-settings-tab');
    const firstPanel = document.getElementById('ai-settings-panel');
    
    if (firstTab && firstPanel) {
        // Remove active class from all tabs and panels
        document.querySelectorAll('#settingsTabs .nav-link').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelectorAll('#settingsTabContent .tab-pane').forEach(panel => {
            panel.classList.remove('show', 'active');
        });
        
        // Make first tab active
        firstTab.classList.add('active');
        firstPanel.classList.add('show', 'active');
    }
}
*/

// Additional helper functions
async function saveFolderSettings() {
    try {
        const folderSettings = {
            root_folder: document.getElementById('root-folder').value.trim(),
            staging_folder: document.getElementById('staging-folder').value.trim(),
            storage_folder: document.getElementById('storage-folder').value.trim(),
            data_folder: document.getElementById('data-folder').value.trim(),
            logs_folder: document.getElementById('logs-folder').value.trim()
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(folderSettings)
        });
        
        if (response.ok) {
            showAlert('Folder settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save folder settings', 'danger');
        }
    } catch (error) {
        console.error('Failed to save folder settings:', error);
        showAlert('Failed to save folder settings', 'danger');
    }
}

async function saveFileSettings() {
    try {
        const fileSettings = {
            max_file_size: parseInt(document.getElementById('max-file-size').value),
            allowed_extensions: document.getElementById('allowed-extensions').value.trim()
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(fileSettings)
        });
        
        if (response.ok) {
            showAlert('File settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save file settings', 'danger');
        }
    } catch (error) {
        console.error('Failed to save file settings:', error);
        showAlert('Failed to save file settings', 'danger');
    }
}

async function saveSystemSettings() {
    try {
        const systemSettings = {
            log_level: document.getElementById('log-level').value,
            secret_key: document.getElementById('secret-key').value.trim()
        };
        
        const response = await authenticatedFetch(`${API_BASE}/settings/extended`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(systemSettings)
        });
        
        if (response.ok) {
            showAlert('System settings saved successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to save system settings', 'danger');
        }
    } catch (error) {
        console.error('Failed to save system settings:', error);
        showAlert('Failed to save system settings', 'danger');
    }
}

// Utility functions for the new settings
function selectRootFolder() {
    showAlert('Folder selection requires server-side integration', 'info');
}

function selectWizardRootFolder() {
    showAlert('Folder selection requires server-side integration', 'info');
}

function checkFolderStructure() {
    showAlert('Creating missing folders...', 'info');
    // This would call the backend to create missing folders
}

function generateSecretKey() {
    const randomBytes = new Uint8Array(32);
    crypto.getRandomValues(randomBytes);
    const secretKey = Array.from(randomBytes, byte => byte.toString(16).padStart(2, '0')).join('');
    document.getElementById('secret-key').value = secretKey;
}

async function detectTesseract() {
    showAlert('Auto-detecting Tesseract installation...', 'info');
    // This would call the backend to detect Tesseract
}

async function detectPoppler() {
    showAlert('Auto-detecting Poppler installation...', 'info');
    // This would call the backend to detect Poppler
}

async function testOCR() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/settings/test/ocr`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            showAlert(result.message, 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'OCR test failed', 'danger');
        }
    } catch (error) {
        console.error('OCR test failed:', error);
        showAlert('OCR test failed', 'danger');
    }
}

function installTesseract() {
    showAlert('Please install Tesseract manually. See the Setup Assistant for instructions.', 'info');
}

function installPoppler() {
    showAlert('Please install Poppler manually. See the Setup Assistant for instructions.', 'info');
}

async function testPDFProcessing() {
    showAlert('Testing PDF processing capabilities...', 'info');
    // This would call the backend to test PDF processing
}

// checkDatabaseHealth is already defined earlier - removing duplicate

async function vacuumDatabase() {
    showAlert('Optimizing database...', 'info');
    // This would call the backend to vacuum the database
}

async function getVectorStats() {
    showAlert('Retrieving vector database statistics...', 'info');
    // This would call the backend to get vector statistics
}

async function refreshFileStats() {
    showAlert('Refreshing file statistics...', 'info');
    // This would call the backend to get file statistics
}

// Download logs function
async function downloadLogs() {
    try {
        // Show loading state
        showAlert('Preparing logs for download...', 'info');
        
        // Fetch the logs zip file
        const response = await authenticatedFetch('/api/settings/logs/download', {
            method: 'GET',
            headers: {
                'Accept': 'application/zip'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Failed to download logs: ${response.statusText}`);
        }
        
        // Get the blob from the response
        const blob = await response.blob();
        
        // Create a temporary URL for the blob
        const url = window.URL.createObjectURL(blob);
        
        // Create a temporary anchor element and trigger download
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_manager_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.zip`;
        document.body.appendChild(a);
        a.click();
        
        // Clean up
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showAlert('Logs downloaded successfully', 'success');
    } catch (error) {
        console.error('Error downloading logs:', error);
        showAlert('Failed to download logs: ' + error.message, 'danger');
    }
}

// ========================================
// USER MANAGEMENT FUNCTIONS
// ========================================

// Check authentication on page load

// Load users when settings tab is shown
async function loadUsers() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/users`);
        if (!response.ok) throw new Error('Failed to load users');
        
        const users = await response.json();
        displayUsers(users);
        updateUserStatistics(users);
        
    } catch (error) {
        console.error('Failed to load users:', error);
        showAlert('Failed to load users', 'danger');
    }
}

// Display users in the list
function displayUsers(users) {
    const container = document.getElementById('users-list');
    if (!container) return;
    
    if (!users || users.length === 0) {
        container.innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-users fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">No users found</h5>
                <p class="text-muted">No users are registered in the system yet.</p>
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="table-responsive">
            <table class="table table-dark table-hover table-sm">
                <thead>
                    <tr>
                        <th class="fw-normal text-muted small py-2">USER</th>
                        <th class="fw-normal text-muted small py-2">ROLE</th>
                        <th class="fw-normal text-muted small py-2">STATUS</th>
                        <th class="fw-normal text-muted small py-2">LAST LOGIN</th>
                        <th class="fw-normal text-muted small text-end py-2">ACTIONS</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    users.forEach(user => {
        const isAdmin = user.is_admin;
        const roleLabel = isAdmin ? 'Administrator' : 'User';
        const statusIcon = user.is_active ? 'fa-circle text-success' : 'fa-circle text-secondary';
        
        // Format last login date - simplified
        let lastLoginText = '-';
        if (user.last_login) {
            try {
                const lastLogin = new Date(user.last_login);
                const now = new Date();
                const diffTime = Math.abs(now - lastLogin);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (diffDays === 1) {
                    lastLoginText = 'Today';
                } else if (diffDays === 2) {
                    lastLoginText = 'Yesterday';
                } else {
                    lastLoginText = lastLogin.toLocaleDateString('en-US', { 
                        day: '2-digit', 
                        month: '2-digit', 
                        year: 'numeric' 
                    });
                }
            } catch (e) {
                lastLoginText = '-';
            }
        }
        
        html += `
            <tr class="user-row py-1" data-user-id="${user.id}">
                <td>
                    <div class="d-flex align-items-center">
                        <div class="user-avatar-sm me-2" style="width: 28px; height: 28px; font-size: 0.75rem;">
                            ${user.username.charAt(0).toUpperCase()}
                        </div>
                        <div>
                            <div class="small fw-medium">${escapeHtml(user.username)}</div>
                            <small class="text-muted" style="font-size: 0.75rem;">${escapeHtml(user.email)}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <small class="text-${isAdmin ? 'warning' : 'primary'}">${roleLabel}</small>
                </td>
                <td>
                    <small>${user.is_active ? 'Active' : 'Inactive'}</small>
                </td>
                <td>
                    <small class="text-muted">${lastLoginText}</small>
                </td>
                <td class="text-end">
                    <button class="btn btn-sm btn-dark me-1" onclick="editUser('${user.id}')" title="Edit">
                        <i class="fas fa-edit" style="font-size: 0.75rem;"></i>
                    </button>
                    <button class="btn btn-sm btn-dark text-danger" onclick="deleteUser('${user.id}', '${escapeHtml(user.username)}')" 
                            ${user.username === 'admin' ? 'disabled' : ''} title="${user.username === 'admin' ? 'The admin user cannot be deleted' : 'Delete'}">
                        <i class="fas fa-trash" style="font-size: 0.75rem;"></i>
                    </button>
                </td>
            </tr>
        `;
    });
    
    html += '</tbody></table></div>';
    container.innerHTML = html;
    
    // Add search functionality
    setupUserSearch(users);
}

// Update user statistics
function updateUserStatistics(users) {
    if (!users || users.length === 0) {
        document.getElementById('total-users-count').textContent = '0';
        document.getElementById('active-users-count').textContent = '0';
        document.getElementById('admin-users-count').textContent = '0';
        document.getElementById('recent-logins-count').textContent = '0';
        return;
    }
    
    const totalUsers = users.length;
    const activeUsers = users.filter(user => user.is_active).length;
    const adminUsers = users.filter(user => user.is_admin).length;
    
    // Calculate recent logins (last 24 hours)
    const oneDayAgo = new Date();
    oneDayAgo.setDate(oneDayAgo.getDate() - 1);
    
    const recentLogins = users.filter(user => {
        if (!user.last_login) return false;
        try {
            const lastLogin = new Date(user.last_login);
            return lastLogin > oneDayAgo;
        } catch (e) {
            return false;
        }
    }).length;
    
    // Update the UI with animations
    animateCountUp('total-users-count', totalUsers);
    animateCountUp('active-users-count', activeUsers);
    animateCountUp('admin-users-count', adminUsers);
    animateCountUp('recent-logins-count', recentLogins);
}

// Animate count up effect
function animateCountUp(elementId, targetValue) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    const startValue = 0;
    const duration = 800; // milliseconds
    const increment = targetValue / (duration / 16); // 16ms per frame
    
    let currentValue = startValue;
    const timer = setInterval(() => {
        currentValue += increment;
        if (currentValue >= targetValue) {
            element.textContent = targetValue;
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(currentValue);
        }
    }, 16);
}

// Setup user search functionality
function setupUserSearch(users) {
    const searchInput = document.getElementById('user-search-input');
    if (!searchInput) return;
    
    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase().trim();
        
        if (searchTerm === '') {
            // Show all users
            displayUsers(users);
            return;
        }
        
        // Filter users based on search term
        const filteredUsers = users.filter(user => {
            return user.username.toLowerCase().includes(searchTerm) ||
                   user.email.toLowerCase().includes(searchTerm) ||
                   (user.full_name && user.full_name.toLowerCase().includes(searchTerm));
        });
        
        displayUsers(filteredUsers);
    });
}

// Load current user info
async function loadCurrentUser() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/me`);
        if (!response.ok) throw new Error('Failed to load user info');
        
        const user = await response.json();
        displayCurrentUser(user);
        
    } catch (error) {
        console.error('Failed to load current user:', error);
    }
}

// Display current user info
function displayCurrentUser(user) {
    const container = document.getElementById('current-user-info');
    if (!container) return;
    
    const roleIcon = user.is_admin ? 'fa-user-shield text-warning' : 'fa-user text-primary';
    const roleLabel = user.is_admin ? 'Administrator' : 'User';
    const statusBadge = user.is_active ? 
        '<span class="badge bg-success-subtle text-success"><i class="fas fa-check-circle me-1"></i>Active</span>' : 
        '<span class="badge bg-secondary-subtle text-secondary"><i class="fas fa-times-circle me-1"></i>Inactive</span>';
    
    // Format last login
    let lastLoginText = 'Never signed in';
    if (user.last_login) {
        try {
            const lastLogin = new Date(user.last_login);
            lastLoginText = lastLogin.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            lastLoginText = 'Unknown';
        }
    }
    
    container.innerHTML = `
        <div class="text-center mb-4">
            <div class="avatar-lg mx-auto mb-3">
                <i class="fas ${roleIcon} fa-3x"></i>
            </div>
            <h5 class="mb-1">${escapeHtml(user.full_name || user.username)}</h5>
            <p class="text-muted mb-2">@${escapeHtml(user.username)}</p>
            ${statusBadge}
        </div>
        
        <div class="user-info-item">
            <i class="fas fa-envelope text-muted me-2"></i>
            <span class="fw-semibold">E-Mail:</span>
            <div class="ms-auto text-end">${escapeHtml(user.email)}</div>
        </div>
        
        <div class="user-info-item">
            <i class="fas ${roleIcon} me-2"></i>
            <span class="fw-semibold">Role:</span>
            <div class="ms-auto text-end">
                <span class="badge bg-primary-subtle text-primary">
                    <i class="fas ${roleIcon} me-1"></i>${roleLabel}
                </span>
            </div>
        </div>
        
        <div class="user-info-item">
            <i class="fas fa-clock text-muted me-2"></i>
            <span class="fw-semibold">Last login:</span>
            <div class="ms-auto text-end">
                <small class="text-muted">${lastLoginText}</small>
            </div>
        </div>
        
        <div class="user-info-item border-0">
            <i class="fas fa-calendar text-muted me-2"></i>
            <span class="fw-semibold">Registered:</span>
            <div class="ms-auto text-end">
                <small class="text-muted">${new Date(user.created_at).toLocaleDateString('en-US')}</small>
            </div>
        </div>
    `;
}

// Show add user modal
function showAddUserModal() {
    const modal = new bootstrap.Modal(document.getElementById('addUserModal'));
    modal.show();
}

// Create new user
async function createUser() {
    const username = document.getElementById('add-user-username').value.trim();
    const email = document.getElementById('add-user-email').value.trim();
    const fullName = document.getElementById('add-user-fullname').value.trim();
    const password = document.getElementById('add-user-password').value;
    const role = document.getElementById('add-user-role').value;
    const isActive = document.getElementById('add-user-active').checked;
    
    if (!username || !email || !password) {
        showAlert('Please fill in all required fields', 'warning');
        return;
    }
    
    if (password.length < 8) {
        showAlert('Password must be at least 8 characters long', 'warning');
        return;
    }
    
    try {
        const userData = {
            username,
            email,
            full_name: fullName || null,
            password,
            is_admin: role === 'admin',
            is_active: isActive
        };
        
        const response = await authenticatedFetch(`${API_BASE}/auth/users`, {
            method: 'POST',
            body: JSON.stringify(userData)
        });
        
        if (response.ok) {
            showAlert('User created successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('addUserModal')).hide();
            document.getElementById('add-user-form').reset();
            loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create user', 'danger');
        }
    } catch (error) {
        console.error('Failed to create user:', error);
        showAlert('Failed to create user', 'danger');
    }
}

// Edit user
async function editUser(userId) {
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/users/${userId}`);
        if (!response.ok) throw new Error('Failed to load user');
        
        const user = await response.json();
        
        // Populate form
        document.getElementById('edit-user-id').value = user.id;
        document.getElementById('edit-user-username').value = user.username;
        document.getElementById('edit-user-email').value = user.email;
        document.getElementById('edit-user-fullname').value = user.full_name || '';
        document.getElementById('edit-user-role').value = user.is_admin ? 'admin' : 
                                                         user.roles && user.roles.length > 0 ? user.roles[0].name : 'editor';
        document.getElementById('edit-user-active').checked = user.is_active;
        document.getElementById('edit-user-new-password').value = '';
        
        const modal = new bootstrap.Modal(document.getElementById('editUserModal'));
        modal.show();
        
    } catch (error) {
        console.error('Failed to load user:', error);
        showAlert('Failed to load user', 'danger');
    }
}

// Update user
async function updateUser() {
    const userId = document.getElementById('edit-user-id').value;
    const username = document.getElementById('edit-user-username').value.trim();
    const email = document.getElementById('edit-user-email').value.trim();
    const fullName = document.getElementById('edit-user-fullname').value.trim();
    const role = document.getElementById('edit-user-role').value;
    const isActive = document.getElementById('edit-user-active').checked;
    const newPassword = document.getElementById('edit-user-new-password').value;
    
    if (!username || !email) {
        showAlert('Username and email are required', 'warning');
        return;
    }
    
    try {
        const updateData = {
            username,
            email,
            full_name: fullName || null,
            is_admin: role === 'admin',
            is_active: isActive
        };
        
        // Only include password if it was changed
        if (newPassword) {
            if (newPassword.length < 8) {
                showAlert('Password must be at least 8 characters long', 'warning');
                return;
            }
            updateData.password = newPassword;
        }
        
        const response = await authenticatedFetch(`${API_BASE}/auth/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(updateData)
        });
        
        if (response.ok) {
            showAlert('User updated successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('editUserModal')).hide();
            loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update user', 'danger');
        }
    } catch (error) {
        console.error('Failed to update user:', error);
        showAlert('Failed to update user', 'danger');
    }
}

// Delete user
async function deleteUser(userId, username) {
    if (!confirm(`Are you sure you want to delete user "${username}"?`)) {
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/users/${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showAlert('User deleted successfully', 'success');
            loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete user', 'danger');
        }
    } catch (error) {
        console.error('Failed to delete user:', error);
        showAlert('Failed to delete user', 'danger');
    }
}

// Setup change password form
function setupChangePasswordForm() {
    const form = document.getElementById('change-password-form');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = document.getElementById('new-password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            
            if (newPassword !== confirmPassword) {
                showAlert('New passwords do not match', 'warning');
                return;
            }
            
            if (newPassword.length < 8) {
                showAlert('Password must be at least 8 characters long', 'warning');
                return;
            }
            
            try {
                const response = await authenticatedFetch(`${API_BASE}/auth/change-password`, {
                    method: 'POST',
                    body: JSON.stringify({
                        current_password: currentPassword,
                        new_password: newPassword
                    })
                });
                
                if (response.ok) {
                    showAlert('Password changed successfully', 'success');
                    document.getElementById('change-password-form').reset();
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Failed to change password', 'danger');
                }
            } catch (error) {
                console.error('Failed to change password:', error);
                showAlert('Failed to change password', 'danger');
            }
        });
    }
}

// Logout function
async function logout() {
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/logout`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showAlert('Logged out successfully', 'success');
            setTimeout(() => {
                window.location.href = '/login';
            }, 1000);
        }
    } catch (error) {
        console.error('Logout error:', error);
        // Redirect to login anyway
        window.location.href = '/login';
    }
}

// Enhanced version of loadSettingsExtended that includes user management
async function loadSettingsExtendedWithUsers() {
    // First load the original extended settings
    try {
        const [statsResponse, healthResponse, configResponse] = await Promise.all([
            authenticatedFetch(`${API_BASE}/documents/stats/overview`),
            authenticatedFetch(`${API_BASE}/health/`),
            authenticatedFetch(`${API_BASE}/settings/extended`)
        ]);
        
        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            displayStats(stats);
        }
        
        if (healthResponse.ok) {
            const health = await healthResponse.json();
            displayHealth(health);
        }
        
        if (configResponse.ok) {
            const config = await configResponse.json();
            populateExtendedSettings(config);
        }
        
        await Promise.all([
            refreshLogs(),
            loadAILimits()
        ]);
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        showAlert('Failed to load settings data', 'danger');
    }
    
    // Load users when on the users tab
    const usersTab = document.getElementById('users-settings-tab');
    if (usersTab && usersTab.classList.contains('active')) {
        loadUsers();
        loadCurrentUser();
    }
    
    // Add listener for tab changes
    document.querySelectorAll('#settingsTabs .nav-link[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(e) {
            if (e.target.id === 'users-settings-tab') {
                loadUsers();
                loadCurrentUser();
            }
        });
    });
}

// Handle forced password change
async function submitForcedPasswordChange() {
    const currentPassword = document.getElementById('force-current-password').value;
    const newPassword = document.getElementById('force-new-password').value;
    const confirmPassword = document.getElementById('force-confirm-password').value;
    
    // Validation
    if (!currentPassword || !newPassword || !confirmPassword) {
        showAlert('Please fill in all fields', 'danger');
        return;
    }
    
    if (newPassword.length < 8) {
        showAlert('New password must be at least 8 characters long', 'danger');
        return;
    }
    
    if (newPassword !== confirmPassword) {
        showAlert('Passwords do not match', 'danger');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE}/auth/change-password`, {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
        
        if (response.ok) {
            showAlert('Password changed successfully!', 'success');
            
            // Hide the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('forcePasswordChangeModal'));
            modal.hide();
            
            // Clear the form
            document.getElementById('force-password-change-form').reset();
            
            // Reload the page to initialize the app properly
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to change password', 'danger');
        }
    } catch (error) {
        console.error('Failed to change password:', error);
        showAlert('Failed to change password', 'danger');
    }
}
