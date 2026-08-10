from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timedelta
from loguru import logger
import unicodedata
import time

from ..config import get_settings
from ..models import Document, Correspondent, DocType, Tag
from ..schemas import SearchRequest, SearchResult, SearchFilters, RAGRequest, RAGResponse
from .vector_db_service import VectorDBService
from .ai_service import AIService
from .fuzzy_search import FuzzyMatcher

class SearchService:
    """Comprehensive search service with full-text and semantic search"""
    
    def __init__(self, db: Session = None):
        self.vector_db = VectorDBService(db)
        try:
            # Use a fresh session for AI service initialization if none provided
            if db is None:
                from ..database import SessionLocal
                with SessionLocal() as session:
                    self.ai_service = AIService(db_session=session)
            else:
                self.ai_service = AIService(db_session=db)
        except ValueError as e:
            if "API key" in str(e):
                logger.warning("AI service not available - search will use database-only mode")
                self.ai_service = None
            else:
                raise
        self.fuzzy_matcher = FuzzyMatcher()
        
        # Circuit breaker for AI service
        self._ai_failure_count = 0
        self._ai_failure_threshold = 3  # Failures before circuit opens
        self._ai_circuit_open_until = 0  # Timestamp when circuit can be tried again
        self._ai_circuit_timeout = 300  # 5 minutes circuit breaker timeout
        
        # Predefined date ranges
        self.date_ranges = {
            "today": {"days": 0},
            "yesterday": {"days": 1, "end_days": 1},
            "last_7_days": {"days": 7},
            "last_30_days": {"days": 30},
            "last_90_days": {"days": 90},
            "this_week": {"week_offset": 0},
            "last_week": {"week_offset": 1},
            "this_month": {"month_offset": 0},
            "last_month": {"month_offset": 1},
            "this_quarter": {"quarter_offset": 0},
            "last_quarter": {"quarter_offset": 1},
            "this_year": {"year_offset": 0},
            "last_year": {"year_offset": 1},
            "last_2_years": {"days": 730},
        }
    
    def _calculate_date_range(self, range_key: str) -> tuple[Optional[datetime], Optional[datetime]]:
        """Calculate start and end dates for predefined range"""
        if range_key not in self.date_ranges:
            return None, None
            
        now = datetime.now()
        range_config = self.date_ranges[range_key]
        
        # Handle simple day-based ranges
        if "days" in range_config:
            days = range_config["days"]
            if days == 0:  # today
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                
            # Handle yesterday specifically
            if "end_days" in range_config:
                end_date = (now - timedelta(days=range_config["end_days"])).replace(hour=23, minute=59, second=59, microsecond=999999)
                
            return start_date, end_date
            
        # Handle week-based ranges
        elif "week_offset" in range_config:
            offset = range_config["week_offset"]
            # Monday = 0, Sunday = 6
            days_since_monday = now.weekday()
            
            if offset == 0:  # this week
                start_date = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = (start_date + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:  # last week
                start_date = (now - timedelta(days=days_since_monday + 7 * offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = (start_date + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
                
            return start_date, end_date
            
        # Handle month-based ranges
        elif "month_offset" in range_config:
            offset = range_config["month_offset"]
            
            if offset == 0:  # this month
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if now.month == 12:
                    end_date = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                else:
                    end_date = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:  # last month
                if now.month == 1:
                    start_date = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
                    end_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                else:
                    start_date = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
                    end_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                    
            return start_date, end_date
            
        # Handle quarter-based ranges
        elif "quarter_offset" in range_config:
            offset = range_config["quarter_offset"]
            quarter = (now.month - 1) // 3 + 1
            
            if offset == 0:  # this quarter
                quarter_start_month = (quarter - 1) * 3 + 1
                start_date = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
                
                if quarter == 4:
                    end_date = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                else:
                    end_date = now.replace(month=quarter_start_month + 3, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:  # last quarter
                if quarter == 1:
                    start_date = now.replace(year=now.year - 1, month=10, day=1, hour=0, minute=0, second=0, microsecond=0)
                    end_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                else:
                    quarter_start_month = (quarter - 2) * 3 + 1
                    start_date = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
                    end_date = now.replace(month=(quarter - 1) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                    
            return start_date, end_date
            
        # Handle year-based ranges
        elif "year_offset" in range_config:
            offset = range_config["year_offset"]
            
            if offset == 0:  # this year
                start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:  # last year
                start_date = now.replace(year=now.year - offset, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(year=now.year - offset + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
                
            return start_date, end_date
            
        return None, None
    
    def _is_ai_circuit_open(self) -> bool:
        """Check if AI circuit breaker is open"""
        if self._ai_circuit_open_until > time.time():
            return True
        
        # If timeout has passed, reset failure count
        if self._ai_circuit_open_until > 0 and time.time() > self._ai_circuit_open_until:
            logger.info("AI circuit breaker timeout expired, resetting failure count")
            self._ai_failure_count = 0
            self._ai_circuit_open_until = 0
        
        return False
    
    def _record_ai_failure(self):
        """Record an AI service failure and potentially open circuit breaker"""
        self._ai_failure_count += 1
        logger.warning(f"AI service failure #{self._ai_failure_count}")
        
        if self._ai_failure_count >= self._ai_failure_threshold:
            self._ai_circuit_open_until = time.time() + self._ai_circuit_timeout
            logger.error(f"AI circuit breaker opened for {self._ai_circuit_timeout}s after {self._ai_failure_count} failures")
    
    def _record_ai_success(self):
        """Record an AI service success and reset failure count"""
        if self._ai_failure_count > 0:
            logger.info("AI service recovered, resetting failure count")
            self._ai_failure_count = 0
            self._ai_circuit_open_until = 0
    
    def _normalize_text_for_search(self, text: str) -> str:
        """Normalize text for better search matching by folding accented characters"""
        if not text:
            return text
        
        # Convert to lowercase
        text = text.lower()
        
        # Normalize Unicode characters (NFD = decomposed form)
        text = unicodedata.normalize('NFD', text)
        
        # Fold accented characters down to their ASCII form so a query typed on
        # an English keyboard still matches text scanned from any document.
        char_map = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
            'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'å': 'a',
            'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
            'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
            'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o',
            'ù': 'u', 'ú': 'u', 'û': 'u',
            'ñ': 'n', 'ç': 'c'
        }
        
        # Apply character mapping
        for original, replacement in char_map.items():
            text = text.replace(original, replacement)
        
        return text
    
    def _create_search_variants(self, query: str) -> List[str]:
        """Create search variants including typo variants for fuzzy search"""
        # Generate fuzzy variants using the fuzzy matcher
        fuzzy_variants = self.fuzzy_matcher.generate_typo_variants(query)
        
        # Convert set to list and limit the number of variants
        # Prioritize: original query, lowercase, then fuzzy variants
        variants = [query]
        if query.lower() != query:
            variants.append(query.lower())
        
        # Add top fuzzy variants (limit to prevent explosion)
        for variant in list(fuzzy_variants)[:10]:
            if variant not in variants:
                variants.append(variant)
        
        logger.debug(f"Generated {len(variants)} search variants for '{query}'")
        return variants
    
    def _enhance_query_for_semantic_search(self, query: str) -> str:
        """Enhance query for better semantic search by adding context with fuzzy matching"""
        enhanced = query
        query_lower = query.lower()
        
        # Common document types and their English synonyms
        doc_type_keywords = {
            'invoice': 'invoice invoices bill billing statement charge',
            'contract': 'contract contracts agreement terms deal',
            'letter': 'letter letters correspondence mail notice',
            'order': 'order orders purchase procurement',
            'quote': 'quote quotation offer proposal estimate',
            'reminder': 'reminder payment reminder overdue dunning notice',
            'delivery': 'delivery delivery note shipment dispatch',
            'receipt': 'receipt receipts proof of payment voucher',
            'certificate': 'certificate certification confirmation attestation',
            'payslip': 'payslip payroll salary wage statement',
            'tax': 'tax taxes tax office tax relevant fiscal',
            'translation': 'translation translator translate translated',
        }
        
        # Check fuzzy matching against document type keywords (use higher threshold to be more precise)
        for keyword, synonyms in doc_type_keywords.items():
            # Check if query fuzzy matches the keyword (be more strict)
            similarity = self.fuzzy_matcher.calculate_similarity(query_lower, keyword)
            if similarity > 0.8:
                enhanced = f"{query} {synonyms}"
                logger.debug(f"Enhanced query with similar document type: {keyword} (similarity: {similarity:.2f})")
                break
            # Also check if keyword fuzzy contains query (more lenient)
            elif self.fuzzy_matcher.fuzzy_contains(keyword, query_lower, threshold=0.8):
                enhanced = f"{query} {synonyms}"
                logger.debug(f"Enhanced query with document type context: {keyword}")
                break
            # Check if query appears in synonyms (for cross-language search)
            elif query_lower in synonyms.lower():
                enhanced = f"{query} {synonyms}"
                logger.debug(f"Enhanced query with cross-language match for '{keyword}'")
                break
        
        # Add temporal context for date-related queries with fuzzy matching
        time_keywords = {
            'january': 'January Jan 01',
            'february': 'February Feb 02',
            'march': 'March Mar 03',
            'april': 'April Apr 04',
            'may': 'May 05',
            'june': 'June Jun 06',
            'july': 'July Jul 07',
            'august': 'August Aug 08',
            'september': 'September Sep 09',
            'october': 'October Oct 10',
            'november': 'November Nov 11',
            'december': 'December Dec 12',
            '2023': '2023 year',
            '2024': '2024 year',
            '2025': '2025 year'
        }
        
        for keyword, context in time_keywords.items():
            if self.fuzzy_matcher.fuzzy_contains(query_lower, keyword, threshold=0.7):
                enhanced = f"{enhanced} {context} date time period"
                logger.debug(f"Enhanced query with temporal context: {keyword}")
                break
        
        return enhanced
    
    def _expand_query_context(self, query: str) -> str:
        """Expand query with additional context for broader semantic matching"""
        # Generate fuzzy variants of the query
        fuzzy_variants = list(self.fuzzy_matcher.generate_typo_variants(query))[:3]
        
        # Build expanded query with variants
        expanded_parts = [query]
        expanded_parts.extend(fuzzy_variants)
        
        # Add document context
        expanded_parts.append("document file record")

        # Add common business terms for context
        expanded_parts.append("business company organisation")

        # Add action words if they seem implied
        query_lower = query.lower()
        if any(word in query_lower for word in ['find', 'search', 'show', 'where', 'what', 'list']):
            expanded_parts.append("find search show list")
        
        # Join all parts
        expanded = " ".join(expanded_parts)
        
        logger.debug(f"Expanded query from '{query}' to '{expanded[:100]}...'")
        return expanded
    
    def _rerank_results(self, results: List[Dict], original_query: str, limit: int) -> List[Dict]:
        """Re-rank results based on fuzzy matching relevance"""
        if not results:
            return []
        
        query_lower = original_query.lower()
        
        for result in results:
            # Get metadata
            metadata = result.get('metadata', {})
            title = (metadata.get('title') or '').lower()
            doc_text = (result.get('text') or '').lower()
            
            # Calculate fuzzy matching scores
            title_score = self.fuzzy_matcher.calculate_similarity(title, query_lower) if title else 0
            
            # Check if query words appear in title with fuzzy matching
            query_words_boost = 0
            for query_word in query_lower.split():
                if len(query_word) > 2:  # Skip very short terms
                    # Check fuzzy match in title
                    if self.fuzzy_matcher.fuzzy_contains(title, query_word, threshold=0.6):
                        query_words_boost += 0.15
                    # Partial credit for document text
                    elif self.fuzzy_matcher.fuzzy_contains(doc_text[:200], query_word, threshold=0.7):
                        query_words_boost += 0.05
            
            # Combine scores
            original_score = result.get('score', 0)
            fuzzy_boost = (title_score * 0.3) + query_words_boost
            
            # Apply boost with ceiling
            result['score'] = min(1.0, original_score + fuzzy_boost)
            
            # Add relevance explanation for debugging
            result['relevance_details'] = {
                'original_score': original_score,
                'title_similarity': title_score,
                'word_matches': query_words_boost,
                'total_boost': fuzzy_boost
            }
        
        # Re-sort by updated scores
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Return top results
        return results[:limit]
    
    def search_documents(self, search_request: SearchRequest, db: Session) -> SearchResult:
        """Main search function that ALWAYS returns top 20 most similar documents"""
        
        # Start with base query
        base_query = db.query(Document)
        
        # Apply filters to base query
        if search_request.filters:
            base_query = self._apply_filters(base_query, search_request.filters)
        
        # If no text query, return top documents by creation date
        if not search_request.query:
            total_count = base_query.count()
            documents = base_query.order_by(Document.created_at.desc()).offset(search_request.offset).limit(search_request.limit).all()
            
            return SearchResult(
                documents=documents,
                total_count=total_count,
                query=search_request.query,
                filters=search_request.filters
            )
        
        # ALWAYS use vector search and ALWAYS return results
        semantic_results = self._semantic_search(
            search_request.query, 
            search_request.filters,
            max(search_request.limit, 20)  # Always get at least 20 results
        )
        
        # If semantic search returns results, use them
        if semantic_results:
            # Get document IDs from semantic search with scores
            semantic_doc_data = {}
            for result in semantic_results:
                doc_id = result['metadata']['document_id']
                semantic_doc_data[doc_id] = {
                    'score': result.get('score', 0),
                    'rank': len(semantic_doc_data)
                }
            
            # Get documents from database
            documents_query = base_query.filter(Document.id.in_(semantic_doc_data.keys()))
            documents = documents_query.all()
            
            # Sort by semantic similarity score
            documents.sort(key=lambda doc: semantic_doc_data.get(doc.id, {}).get('rank', 999))
            
            # Apply pagination
            total_count = len(documents)
            documents = documents[search_request.offset:search_request.offset + search_request.limit]
            
        else:
            # Fallback: If vector search fails, use full-text search for better relevance
            if self.ai_service:
                logger.warning(f"Vector search failed for query: {search_request.query}, using full-text search")
            else:
                logger.info(f"AI service not available - using full-text search for query: {search_request.query}")
            
            # Use full-text search as fallback
            documents, total_count = self._full_text_search(base_query, search_request)
        
        logger.info(f"Search for '{search_request.query}' returned {len(documents)} documents (total: {total_count})")
        
        return SearchResult(
            documents=documents,
            total_count=total_count,
            query=search_request.query,
            filters=search_request.filters
        )
    
    def _apply_filters(self, query, filters: SearchFilters):
        """Apply filters to the query"""
        
        if filters.correspondent_ids:
            query = query.filter(Document.correspondent_id.in_(filters.correspondent_ids))
        
        if filters.doctype_ids:
            query = query.filter(Document.doctype_id.in_(filters.doctype_ids))
        
        if filters.tag_ids:
            query = query.join(Document.tags).filter(Tag.id.in_(filters.tag_ids))
        
        # Date range filtering - predefined ranges take precedence
        if filters.date_range:
            start_date, end_date = self._calculate_date_range(filters.date_range)
            if start_date and end_date:
                query = query.filter(Document.document_date >= start_date, Document.document_date <= end_date)
                logger.debug(f"Applied date range '{filters.date_range}': {start_date.date()} to {end_date.date()}")
        else:
            # Fallback to custom date range if no predefined range is set
            if filters.date_from:
                try:
                    date_from_parsed = datetime.fromisoformat(filters.date_from)
                    query = query.filter(Document.document_date >= date_from_parsed)
                except ValueError:
                    logger.warning(f"Invalid date_from format: {filters.date_from}")
            
            if filters.date_to:
                try:
                    date_to_parsed = datetime.fromisoformat(filters.date_to)
                    query = query.filter(Document.document_date <= date_to_parsed)
                except ValueError:
                    logger.warning(f"Invalid date_to format: {filters.date_to}")
        
        if filters.is_tax_relevant is not None:
            query = query.filter(Document.is_tax_relevant == filters.is_tax_relevant)
        
        # Reminder filtering - simplified options
        if filters.reminder_filter:
            if filters.reminder_filter == "has":
                query = query.filter(Document.reminder_date.isnot(None))
            elif filters.reminder_filter == "overdue":
                query = query.filter(
                    Document.reminder_date.isnot(None),
                    Document.reminder_date < datetime.now()
                )
            elif filters.reminder_filter == "none":
                query = query.filter(Document.reminder_date.is_(None))
        
        return query
    
    def _full_text_search(self, query, search_request: SearchRequest) -> tuple:
        """Perform full-text search using SQL LIKE with fuzzy variants"""
        # Create fuzzy search variants
        search_variants = self._create_search_variants(search_request.query)
        
        # Also add word-level variants for better matching
        words = search_request.query.lower().split()
        for word in words:
            if len(word) > 3:  # Only for meaningful words
                word_variants = list(self.fuzzy_matcher.generate_typo_variants(word))[:5]
                for variant in word_variants:
                    if variant not in search_variants:
                        search_variants.append(variant)
        
        # Build OR conditions for all variants
        variant_filters = []
        for variant in search_variants[:20]:  # Limit to prevent query explosion
            search_term = f"%{variant}%"
            variant_filters.append(
                or_(
                    Document.title.ilike(search_term),
                    Document.summary.ilike(search_term),
                    Document.full_text.ilike(search_term),
                    Document.filename.ilike(search_term)
                )
            )
        
        # Combine all variant filters with OR
        if variant_filters:
            text_filter = or_(*variant_filters)
            query = query.filter(text_filter)
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination and ordering
        documents = (query
                   .order_by(Document.created_at.desc())
                   .offset(search_request.offset)
                   .limit(search_request.limit)
                   .all())
        
        logger.debug(f"Full-text search with {len(search_variants)} variants returned {total_count} total results")
        return documents, total_count
    
    def _semantic_search(self, query: str, filters: Optional[SearchFilters], limit: int) -> List[Dict]:
        """Perform semantic search that ALWAYS returns results, sorted by similarity"""
        if not self.ai_service:
            logger.info("AI service not available - semantic search disabled")
            return []
        
        # Check circuit breaker
        if self._is_ai_circuit_open():
            remaining_time = int(self._ai_circuit_open_until - time.time())
            logger.warning(f"AI circuit breaker is open - semantic search disabled for {remaining_time}s")
            return []
        
        # Track search start time for timeout detection
        search_start_time = time.time()
        
        try:
            # Enhanced query preprocessing for better semantic understanding
            enhanced_query = self._enhance_query_for_semantic_search(query)
            
            # Create search variants for tolerant character matching
            search_variants = self._create_search_variants(query)
            logger.debug(f"Generated search variants: {search_variants}")
            
            # Set maximum search time to prevent hanging
            max_search_time = 45  # Total search timeout in seconds
            
            # Strategy: Always get results by trying multiple approaches
            all_results = []
            
            # Approach 1: Try composite query with variants
            try:
                # Check if we still have time for this approach
                if time.time() - search_start_time > max_search_time * 0.6:
                    logger.warning("Skipping composite search due to time constraints")
                    raise TimeoutError("Search taking too long")
                
                top_variants = search_variants[:5]
                composite_query = f"{enhanced_query} {' '.join(top_variants)}"
                
                composite_embeddings = self.ai_service.generate_embeddings(composite_query)
                
                # Get ALL available documents from vector DB without filters first
                primary_results = self.vector_db.search_similar(
                    query_embeddings=composite_embeddings,
                    limit=100,  # Get many results to ensure we have options
                    filters=None  # No filters to get maximum results
                )
                
                logger.info(f"Composite search returned {len(primary_results)} raw results")
                all_results.extend(primary_results)
                
            except Exception as e:
                logger.warning(f"Composite search failed: {e}")
            
            # Approach 2: If still no results, try original query only
            if len(all_results) == 0:
                try:
                    # Check if we still have time for this approach
                    if time.time() - search_start_time > max_search_time * 0.8:
                        logger.warning("Skipping original query search due to time constraints")
                        raise TimeoutError("Search taking too long")
                    
                    logger.info("No composite results, trying original query")
                    original_embeddings = self.ai_service.generate_embeddings(query)
                    
                    original_results = self.vector_db.search_similar(
                        query_embeddings=original_embeddings,
                        limit=100,
                        filters=None
                    )
                    
                    logger.info(f"Original query search returned {len(original_results)} results")
                    all_results.extend(original_results)
                    
                except Exception as e:
                    logger.warning(f"Original query search failed: {e}")
            
            # Approach 3: If STILL no results, get ALL documents from vector DB
            if len(all_results) == 0:
                try:
                    # Only try this if we have time left
                    if time.time() - search_start_time > max_search_time * 0.9:
                        logger.warning("Skipping fallback search due to time constraints")
                        return []  # Give up and return empty results
                    
                    logger.warning("No vector results at all, attempting to get any documents from vector DB")
                    
                    # Use a generic embedding to get ALL documents
                    generic_embeddings = self.ai_service.generate_embeddings("document")
                    
                    fallback_results = self.vector_db.search_similar(
                        query_embeddings=generic_embeddings,
                        limit=100,
                        filters=None
                    )
                    
                    logger.info(f"Fallback search returned {len(fallback_results)} results")
                    all_results.extend(fallback_results)
                    
                except Exception as e:
                    logger.error(f"Even fallback search failed: {e}")
                    return []  # This should never happen if vector DB has documents
            
            # Remove duplicates and sort by score
            unique_results = {}
            for result in all_results:
                doc_id = result['metadata']['document_id']
                if doc_id not in unique_results or result.get('score', 0) > unique_results[doc_id].get('score', 0):
                    unique_results[doc_id] = result
            
            # Convert back to list and sort by score (highest first)
            final_results = list(unique_results.values())
            final_results.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            # Apply limit
            final_results = final_results[:limit]
            
            logger.info(f"Semantic search for '{query}' returned {len(final_results)} unique results")
            if final_results:
                logger.debug(f"Score range: {final_results[0].get('score', 0):.3f} - {final_results[-1].get('score', 0):.3f}")
            
            # Record success
            self._record_ai_success()
            
            return final_results
            
        except Exception as e:
            search_duration = time.time() - search_start_time
            if search_duration > max_search_time or "timeout" in str(e).lower():
                logger.error(f"Semantic search timed out after {search_duration:.1f}s: {e}")
            else:
                logger.error(f"Semantic search failed completely after {search_duration:.1f}s: {e}")
            
            # Record AI failure for circuit breaker
            self._record_ai_failure()
            
            return []
    
    def rag_query(self, rag_request: RAGRequest, db: Session) -> RAGResponse:
        """Answer questions using RAG (Retrieval-Augmented Generation)"""
        
        if not self.ai_service:
            provider = (get_settings(db).ai_provider or "groq").lower()
            key_hint = {
                "groq": "GROQ_API_KEY",
                "openai": "OPENAI_API_KEY",
                "azure": "AZURE_OPENAI_API_KEY",
            }.get(provider, "the provider API key")
            return RAGResponse(
                answer=(
                    f"AI service is not available. Configure {key_hint} in .env "
                    "(or under Settings → AI Configuration) to use the chat feature."
                ),
                sources=[],
                confidence=0.0
            )
        
        # Check circuit breaker
        if self._is_ai_circuit_open():
            remaining_time = int(self._ai_circuit_open_until - time.time())
            return RAGResponse(
                answer=f"AI service is temporarily disabled due to repeated failures. Please try again in {remaining_time} seconds.",
                sources=[],
                confidence=0.0
            )
        
        try:
            # Check if manual document selection is used
            if rag_request.document_ids:
                # Manual mode: use specified documents
                from ..models import Document
                documents = db.query(Document).filter(Document.id.in_(rag_request.document_ids)).all()
                search_result = SearchResult(
                    documents=documents,
                    total_count=len(documents),
                    query=rag_request.question,
                    took_ms=0
                )
            else:
                # Auto mode: find relevant documents using semantic search
                search_request = SearchRequest(
                    query=rag_request.question,
                    filters=rag_request.filters,
                    limit=rag_request.max_documents,
                    use_semantic_search=True
                )
                
                search_result = self.search_documents(search_request, db)
            
            if not search_result.documents:
                return RAGResponse(
                    answer="I couldn't find any relevant documents to answer your question.",
                    sources=[],
                    confidence=0.0
                )
            
            # Prepare context for AI.
            #
            # `used_documents` is kept in step with the context, because the
            # model is told to cite as [Doc1], [Doc2] - numbered by position in
            # what it was given. Returning every match as the source list
            # instead would break that mapping the moment one document had no
            # text to send: everything after it would cite the wrong file.
            context_documents = []
            document_titles = []
            document_ids = []
            used_documents = []

            for doc in search_result.documents:
                # Use full document text instead of summary for RAG
                context_text = doc.full_text or doc.summary or ""
                if context_text:
                    context_documents.append(context_text)
                    document_titles.append(doc.title or doc.filename)
                    document_ids.append(str(doc.id))
                    used_documents.append(doc)

            if not context_documents:
                return RAGResponse(
                    answer="The relevant documents don't contain enough text to answer your question.",
                    sources=search_result.documents,
                    confidence=0.0
                )
            
            # Generate answer using AI
            answer = self.ai_service.answer_question(
                question=rag_request.question,
                context_documents=context_documents,
                document_titles=document_titles,
                document_ids=document_ids
            )
            
            # Calculate confidence based on number of relevant documents
            confidence = min(len(context_documents) / rag_request.max_documents, 1.0)
            
            # Record success
            self._record_ai_success()
            
            return RAGResponse(
                answer=answer,
                # The documents actually sent, in the order they were numbered,
                # so [DocN] in the answer is sources[N-1] on the screen.
                sources=used_documents,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            
            # Record AI failure for circuit breaker
            self._record_ai_failure()
            
            return RAGResponse(
                answer=f"I encountered an error while processing your question: {str(e)}",
                sources=[],
                confidence=0.0
            )
    
    def get_search_suggestions(self, partial_query: str, db: Session) -> Dict[str, List[str]]:
        """Get search suggestions based on partial query, tolerant of accented characters"""
        suggestions = {
            "correspondents": [],
            "doctypes": [],
            "tags": [],
            "titles": []
        }
        
        if len(partial_query) < 2:
            return suggestions
        
        # Create search variants for tolerant character matching
        search_variants = self._create_search_variants(partial_query)
        
        try:
            all_results = {key: set() for key in suggestions.keys()}
            
            # Search with all variants
            for variant in search_variants:
                search_term = f"%{variant}%"
                
                # Get correspondent suggestions
                correspondents = (db.query(Correspondent.name)
                                .filter(Correspondent.name.ilike(search_term))
                                .limit(10)
                                .all())
                all_results["correspondents"].update(c[0] for c in correspondents)
                
                # Get doctype suggestions
                doctypes = (db.query(DocType.name)
                           .filter(DocType.name.ilike(search_term))
                           .limit(10)
                           .all())
                all_results["doctypes"].update(d[0] for d in doctypes)
                
                # Get tag suggestions
                tags = (db.query(Tag.name)
                       .filter(Tag.name.ilike(search_term))
                       .limit(10)
                       .all())
                all_results["tags"].update(t[0] for t in tags)
                
                # Get title suggestions
                titles = (db.query(Document.title)
                         .filter(Document.title.ilike(search_term))
                         .filter(Document.title.isnot(None))
                         .limit(10)
                         .all())
                all_results["titles"].update(t[0] for t in titles if t[0])
            
            # Convert sets to lists and limit to 5 each
            for key in suggestions.keys():
                suggestions[key] = list(all_results[key])[:5]
            
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
        
        return suggestions
    
    def get_document_recommendations(self, document_id: str, db: Session, limit: int = 5) -> List[Document]:
        """Get similar documents based on a given document"""
        if not self.ai_service:
            logger.info("AI service not available - document recommendations disabled")
            return []
        
        try:
            # Get the source document
            source_doc = db.query(Document).filter(Document.id == document_id).first()
            if not source_doc or not source_doc.full_text:
                return []
            
            # Use summary or truncated full text for similarity search
            text_for_search = source_doc.summary or source_doc.full_text[:1000]
            
            # Get embeddings and search for similar documents
            query_embeddings = self.ai_service.generate_embeddings(text_for_search)
            
            similar_results = self.vector_db.search_similar(
                query_embeddings=query_embeddings,
                limit=limit + 1  # +1 to exclude the source document
            )
            
            # Get document IDs (excluding the source document)
            similar_doc_ids = [
                result['metadata']['document_id'] 
                for result in similar_results 
                if result['metadata']['document_id'] != document_id
            ][:limit]
            
            if not similar_doc_ids:
                return []
            
            # Fetch documents from database
            similar_docs = (db.query(Document)
                          .filter(Document.id.in_(similar_doc_ids))
                          .all())
            
            # Preserve order from vector search
            doc_id_order = {doc_id: i for i, doc_id in enumerate(similar_doc_ids)}
            similar_docs.sort(key=lambda doc: doc_id_order.get(doc.id, 999))
            
            return similar_docs
            
        except Exception as e:
            logger.error(f"Failed to get document recommendations: {e}")
            return []
