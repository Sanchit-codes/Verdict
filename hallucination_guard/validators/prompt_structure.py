"""Phase 2B: Prompt Structure Analyzer (Tier 0.5)

Parses prompts into StructuredPrompt with intent, language, entities, PII, and sensitivity tags.
This is analysis-only (always returns passed=True) and runs first to enable downstream use.

Target latency: <20ms (keyword-based heuristics, optional ML models)

Implements:
1. Intent classification - question, instruction, statement, creative, chat, system
2. Language detection - simple heuristic or optional langdetect
3. Entity extraction - basic regex or optional spacy
4. PII detection - email, SSN, phone, credit card patterns
5. Sensitivity classification - medical, financial, legal, personal, proprietary keywords
6. Topic extraction - simple keyword-based analysis

Always returns passed=True with score=1.0 (this is analysis, not validation).
Returns structured_prompt in metadata dict for downstream validators to use.
Gracefully degrades on errors - never crashes the pipeline.
"""

import logging
import re
import time
from typing import Optional

from hallucination_guard.prompts.schema import PromptIntent, PromptSensitivity, StructuredPrompt

from .base import BaseValidator, ValidationInput, ValidationResult

logger = logging.getLogger(__name__)


class PromptStructureValidator(BaseValidator):
    """Analyzes prompt structure and extracts metadata for downstream validators.
    
    This validator is intentionally analysis-only and always returns passed=True.
    Its purpose is to extract rich metadata about the prompt (intent, PII, sensitivity)
    that downstream validators can use in their decisions.
    
    Works with or without optional dependencies (langdetect, spacy).
    Gracefully degrades on any error - never crashes the pipeline.
    """
    
    # Intent detection keywords
    QUESTION_KEYWORDS = {"what", "why", "how", "when", "where", "which", "who", "whose", 
                         "can you", "could you", "do you", "does", "is", "are", "would you", "will you"}
    
    INSTRUCTION_KEYWORDS = {"generate", "write", "create", "extract", "summarize", "list", 
                           "explain", "describe", "tell", "show", "provide", "give", "analyze"}
    
    CREATIVE_KEYWORDS = {"write", "story", "poem", "imagine", "creative", "fiction", 
                        "compose", "author", "craft"}
    
    CHAT_KEYWORDS = {"hello", "hi", "hey", "thanks", "thank you", "please", "tell me about",
                    "what about", "how about", "talk", "discuss"}
    
    SYSTEM_KEYWORDS = {"you are", "system prompt", "jailbreak", "ignore", "bypass", "override",
                      "forget", "don't", "don't mention", "pretend", "act as", "role play"}
    
    # PII detection patterns
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    }
    
    # Sensitivity keywords by domain
    SENSITIVITY_KEYWORDS = {
        "medical": ["patient", "doctor", "hospital", "diagnosis", "medication", "treatment", 
                   "disease", "symptom", "prescription", "clinical", "medical", "health",
                   "illness", "healthcare", "surgical", "therapy"],
        "financial": ["account", "bank", "credit", "loan", "investment", "portfolio", "stock",
                     "mortgage", "banking", "financial", "money", "payment", "transaction",
                     "currency", "profit", "revenue", "income"],
        "legal": ["attorney", "contract", "lawsuit", "subpoena", "legal advice", "court",
                 "jurisdiction", "law", "legislation", "statute", "compliance", "regulation",
                 "agreement", "terms", "liability"],
        "personal": ["password", "secret", "private", "personal", "confidential", "ssn",
                    "credit card", "passport", "driver's license", "social security",
                    "intimate", "private information"],
        "proprietary": ["trade secret", "confidential", "patent", "nda", "intellectual property",
                       "proprietary", "classified", "restricted", "confidentiality"],
    }
    
    def __init__(self, config: dict[str, object]) -> None:
        """Initialize prompt structure validator.
        
        Args:
            config: Configuration dict (flexible, no required keys for MVP)
        """
        super().__init__(config)
        self.confidence = config.get("confidence", 0.95)
        # Lazy-load optional dependencies if available
        self.langdetect_available = False
        self.spacy_available = False
        self.spacy_nlp: object = None
        self._try_load_optional_deps()
    
    def _try_load_optional_deps(self) -> None:
        """Try to load optional ML dependencies without crashing if unavailable."""
        try:
            import langdetect  # type: ignore[import-not-found]
            self.langdetect_available = True
        except ImportError:
            logger.debug("langdetect not available, using heuristic language detection")
        
        try:
            import spacy  # type: ignore[import-not-found]
            self.spacy_nlp = spacy.load("en_core_web_sm")
            self.spacy_available = True
        except (ImportError, OSError):
            logger.debug("spacy not available, using regex-based entity extraction")
    
    def is_available(self) -> bool:
        """Always available - works with or without optional ML models.
        
        Returns:
            True (this validator has no mandatory dependencies)
        """
        return True
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Analyze prompt and return StructuredPrompt in metadata.
        
        Always returns passed=True (this is analysis, not validation).
        All analysis errors gracefully degrade - never crashes.
        
        Args:
            input: ValidationInput with prompt text
        
        Returns:
            ValidationResult with score=1.0, passed=True, structured_prompt in metadata
        """
        start_time = time.perf_counter()
        
        try:
            # Perform all analyses with graceful error handling
            prompt_text = input.prompt or ""
            
            intent = self._classify_intent(prompt_text)
            language = self._detect_language(prompt_text)
            entities = self._extract_entities(prompt_text)
            pii_findings = self._detect_pii(prompt_text)
            sensitivity_tags = self._classify_sensitivity(prompt_text, input.domain or "")
            topics = self._extract_topics(prompt_text)
            
            # Build StructuredPrompt
            structured_prompt = StructuredPrompt(
                original_text=prompt_text,
                intent=intent,
                sensitivity=sensitivity_tags[0] if sensitivity_tags else PromptSensitivity.PUBLIC,
                has_context_switching=False,  # Set by prompt_injection validator later
                has_role_injection=False,     # Set by prompt_injection validator later
                has_chain_of_thought_injection=False,  # Set by prompt_injection validator later
                detected_keywords=[],  # Set by prompt_injection validator later
                risk_score=0.0,  # Set by prompt_injection validator later
                metadata={
                    "language": language,
                    "token_count": len(prompt_text.split()),
                    "char_count": len(prompt_text),
                    "entities": entities,
                    "pii_findings": pii_findings,
                    "sensitivity_tags": [tag.value for tag in sensitivity_tags],
                    "topics": topics,
                    "contains_pii": len(pii_findings) > 0,
                    "confidence": self.confidence,
                }
            )
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            # Always return passed=True with evidence
            evidence = (
                f"Prompt analysis: intent={intent.value}, language={language}, "
                f"sensitivity={','.join(tag.value for tag in sensitivity_tags)}, "
                f"pii_found={'yes' if pii_findings else 'no'}"
            )
            
            return ValidationResult(
                validator_name="prompt_structure",
                score=1.0,  # Analysis always passes
                passed=True,  # This is analysis, not validation
                evidence=evidence,
                latency_ms=latency_ms,
                metadata={"structured_prompt": structured_prompt.model_dump()}
            )
        
        except Exception as e:
            # Graceful degradation - return neutral analysis
            logger.warning(f"Prompt structure analysis failed, returning neutral: {e}")
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            # Return a minimal StructuredPrompt on error
            structured_prompt = StructuredPrompt(
                original_text=input.prompt or "",
                intent=PromptIntent.QUESTION,
                sensitivity=PromptSensitivity.PUBLIC,
                metadata={"error": str(e), "confidence": 0.0}
            )
            
            return ValidationResult(
                validator_name="prompt_structure",
                score=1.0,  # Still passes (analysis is forgiving)
                passed=True,
                evidence=f"Prompt analysis degraded: {str(e)}",
                latency_ms=latency_ms,
                error=str(e),
                metadata={"structured_prompt": structured_prompt.model_dump()}
            )
    
    def _classify_intent(self, prompt: str) -> PromptIntent:
        """Classify prompt intent using keyword matching.
        
        Checks for keywords in order: SYSTEM (highest risk), CREATIVE, INSTRUCTION,
        QUESTION, CHAT, STATEMENT (default).
        
        Args:
            prompt: The prompt text to analyze
        
        Returns:
            PromptIntent enum value
        """
        if not prompt:
            return PromptIntent.QUESTION
        
        prompt_lower = prompt.lower().strip()
        
        # Check SYSTEM intent first (highest risk signal)
        if any(kw in prompt_lower for kw in self.SYSTEM_KEYWORDS):
            return PromptIntent.SYSTEM
        
        # Check CREATIVE intent
        if any(kw in prompt_lower for kw in self.CREATIVE_KEYWORDS):
            return PromptIntent.CREATIVE
        
        # Check INSTRUCTION intent
        if any(kw in prompt_lower for kw in self.INSTRUCTION_KEYWORDS):
            return PromptIntent.INSTRUCTION
        
        # Check QUESTION intent (starts with question word or ends with ?)
        if prompt_lower.endswith("?"):
            return PromptIntent.QUESTION
        if any(prompt_lower.startswith(kw) for kw in self.QUESTION_KEYWORDS):
            return PromptIntent.QUESTION
        
        # Check CHAT intent
        if any(kw in prompt_lower for kw in self.CHAT_KEYWORDS):
            return PromptIntent.CHAT
        
        # Default to STATEMENT
        return PromptIntent.STATEMENT
    
    def _detect_language(self, prompt: str) -> str:
        """Detect language using optional langdetect or heuristic fallback.
        
        Args:
            prompt: The prompt text
        
        Returns:
            Language code (e.g., 'en', 'fr', 'es') or 'unknown'
        """
        if not prompt:
            return "unknown"
        
        # Try langdetect if available
        if self.langdetect_available:
            try:
                from langdetect import detect, LangDetectException  # type: ignore[import-not-found]
                return detect(prompt)  # type: ignore[no-any-return]
            except (LangDetectException, Exception):
                pass  # Fall through to heuristic
        
        # Heuristic: check for common English patterns
        english_words = {"the", "a", "an", "is", "are", "was", "were", "be", "have", "has",
                        "do", "does", "did", "will", "would", "could", "should", "can",
                        "may", "might", "must", "and", "or", "but", "not", "no"}
        
        words = set(prompt.lower().split())
        english_ratio = len(words & english_words) / max(len(words), 1)
        
        if english_ratio > 0.1:  # At least 10% English words
            return "en"
        
        # Default to unknown
        return "unknown"
    
    def _extract_entities(self, prompt: str) -> list[str]:
        """Extract entities using optional spacy or regex fallback.
        
        Args:
            prompt: The prompt text
        
        Returns:
            List of extracted entities
        """
        if not prompt:
            return []
        
        # Try spacy if available
        if self.spacy_available:
            try:
                doc = self.spacy_nlp(prompt[:1000])  # type: ignore[operator]
                return list(set(ent.text for ent in doc.ents))
            except Exception:
                pass  # Fall through to regex
        
        # Regex fallback: extract capitalized phrases (proxy for named entities)
        entity_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
        entities = entity_pattern.findall(prompt)
        
        # Deduplicate and return
        return list(set(entities))
    
    def _detect_pii(self, prompt: str) -> dict[str, list[str]]:
        """Detect PII patterns in prompt.
        
        Args:
            prompt: The prompt text
        
        Returns:
            Dict mapping PII type to list of found values
        """
        if not prompt:
            return {}
        
        pii_findings = {}
        
        try:
            for pii_type, pattern in self.PII_PATTERNS.items():
                matches = re.findall(pattern, prompt)
                if matches:
                    pii_findings[pii_type] = matches
        except Exception as e:
            logger.debug(f"PII detection error: {e}")
        
        return pii_findings
    
    def _classify_sensitivity(self, prompt: str, domain: str) -> list[PromptSensitivity]:
        """Classify prompt sensitivity using keyword matching.
        
        Args:
            prompt: The prompt text
            domain: Optional domain metadata (e.g., 'healthcare')
        
        Returns:
            List of PromptSensitivity tags (may be multiple)
        """
        if not prompt:
            return [PromptSensitivity.PUBLIC]
        
        prompt_lower = prompt.lower()
        domain_lower = (domain or "").lower()
        
        sensitivity_tags = []
        
        # Check each sensitivity category
        for category, keywords in self.SENSITIVITY_KEYWORDS.items():
            if any(kw in prompt_lower for kw in keywords) or category in domain_lower:
                # Map category to PromptSensitivity enum
                sensitivity_map = {
                    "medical": PromptSensitivity.MEDICAL,
                    "financial": PromptSensitivity.FINANCIAL,
                    "legal": PromptSensitivity.LEGAL,
                    "personal": PromptSensitivity.PERSONAL,
                    "proprietary": PromptSensitivity.PROPRIETARY,
                }
                if category in sensitivity_map:
                    sensitivity_tags.append(sensitivity_map[category])
        
        # Always include at least PUBLIC, or return most restrictive sensitivity
        if not sensitivity_tags:
            return [PromptSensitivity.PUBLIC]
        
        # Return tags sorted by sensitivity level (most restrictive first)
        sensitivity_order = [
            PromptSensitivity.LEGAL,
            PromptSensitivity.PROPRIETARY,
            PromptSensitivity.PERSONAL,
            PromptSensitivity.MEDICAL,
            PromptSensitivity.FINANCIAL,
            PromptSensitivity.PUBLIC,
        ]
        
        return sorted(set(sensitivity_tags), key=lambda x: sensitivity_order.index(x))
    
    def _extract_topics(self, prompt: str) -> list[str]:
        """Extract main topics using simple keyword-based analysis.
        
        Args:
            prompt: The prompt text
        
        Returns:
            List of extracted topic keywords
        """
        if not prompt:
            return []
        
        try:
            # Simple TF-based approach: extract frequent meaningful words
            words = prompt.lower().split()
            
            # Filter out common stop words
            stop_words = {
                "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
                "of", "is", "are", "was", "were", "be", "have", "has", "do", "does",
                "did", "will", "would", "could", "should", "may", "might", "must",
                "can", "i", "you", "he", "she", "it", "we", "they", "what", "which",
                "who", "where", "when", "why", "how", "as", "if", "so", "by", "with",
                "this", "that", "these", "those", "my", "your", "his", "her", "its",
                "our", "their", "not", "no", "yes", "just", "only", "very", "more",
                "most", "some", "any", "all", "each", "every", "both", "either"
            }
            
            # Count word frequencies (excluding stop words and short words)
            word_freq: dict[str, int] = {}
            for word in words:
                # Clean punctuation
                word = re.sub(r"[^\w]", "", word)
                if word and len(word) > 2 and word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # Extract top topics (words appearing 2+ times or high value keywords)
            topics = [word for word, freq in word_freq.items() if freq >= 2]
            
            # Limit to top 10 topics
            return sorted(topics, key=lambda w: word_freq[w], reverse=True)[:10]
        
        except Exception as e:
            logger.debug(f"Topic extraction error: {e}")
            return []
