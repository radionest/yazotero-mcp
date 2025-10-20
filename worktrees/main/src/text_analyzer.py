import re

from .models import MethodsAnalysis, TextSummary


class TextAnalyzer:
    """Simple text analysis for research evaluation."""

    def summarize(self, fulltext: str, abstract: str | None = None) -> TextSummary:
        """Create research summary."""
        # Extract sections
        sections = self._extract_sections(fulltext)

        return TextSummary(
            abstract=abstract or self._extract_abstract(fulltext),
            introduction=self._summarize_section(sections.get("introduction", ""), max_sentences=3),
            methods=self._summarize_section(sections.get("methods", ""), max_sentences=3),
            results=self._summarize_section(sections.get("results", ""), max_sentences=3),
            conclusion=self._summarize_section(sections.get("conclusion", ""), max_sentences=3),
            word_count=len(fulltext.split()),
            sections_found=list(sections.keys()),
        )

    def extract_key_points(self, fulltext: str) -> list[str]:
        """Extract key research points."""
        points = []

        # Find sentences with key phrases
        key_phrases = [
            "we found",
            "results show",
            "demonstrated that",
            "significant",
            "conclude that",
            "importantly",
            "novel",
            "first time",
            "main contribution",
        ]

        sentences = fulltext.split(".")
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(phrase in sentence_lower for phrase in key_phrases):
                clean_sentence = sentence.strip()
                if len(clean_sentence) > 20 and len(clean_sentence) < 300:
                    points.append(clean_sentence)

        return points[:10]  # Return top 10 key points

    def extract_methods(self, fulltext: str) -> MethodsAnalysis:
        """Extract methodology information."""
        sections = self._extract_sections(fulltext)
        methods_text = sections.get("methods", "")

        return MethodsAnalysis(
            study_type=self._detect_study_type(methods_text),
            sample_size=self._extract_sample_size(methods_text),
            statistical_methods=self._extract_statistics(methods_text),
            summary=self._summarize_section(methods_text, max_sentences=5),
        )

    def basic_analysis(self, fulltext: str) -> list[str]:
        """Basic analysis returning key points."""
        return self.extract_key_points(fulltext)

    def _extract_sections(self, text: str) -> dict[str, str]:
        """Extract standard paper sections."""
        sections = {}

        # Common section headers
        section_patterns = {
            "introduction": r"(?i)\n(introduction|background)\s*\n",
            "methods": r"(?i)\n(methods?|methodology|materials?\s+and\s+methods?)\s*\n",
            "results": r"(?i)\n(results?|findings)\s*\n",
            "discussion": r"(?i)\n(discussion)\s*\n",
            "conclusion": r"(?i)\n(conclusions?|summary)\s*\n",
        }

        for section, pattern in section_patterns.items():
            match = re.search(pattern, text)
            if match:
                start = match.end()
                # Find next section or end of text
                next_section = re.search(
                    r"(?i)\n(introduction|methods?|results?|discussion|conclusions?)\s*\n",
                    text[start:],
                )
                end = start + next_section.start() if next_section else len(text)
                sections[section] = text[start:end].strip()

        return sections

    def _summarize_section(self, text: str, max_sentences: int = 3) -> str:
        """Simple extractive summarization."""
        if not text:
            return ""

        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
        return ". ".join(sentences[:max_sentences]) + "." if sentences else ""

    def _extract_abstract(self, text: str) -> str:
        """Extract abstract from full text."""
        # Look for abstract section
        abstract_match = re.search(r"(?i)abstract\s*\n(.*?)\n\s*\n", text, re.DOTALL)
        if abstract_match:
            return abstract_match.group(1).strip()

        # Fallback: return first paragraph
        paragraphs = text.split("\n\n")
        if paragraphs:
            return paragraphs[0].strip()[:500]  # First 500 chars

        return ""

    def _detect_study_type(self, methods_text: str) -> str:
        """Detect type of study from methods."""
        text_lower = methods_text.lower()

        if "randomized" in text_lower and "trial" in text_lower:
            return "RCT"
        elif "cohort" in text_lower:
            return "Cohort Study"
        elif "case-control" in text_lower:
            return "Case-Control Study"
        elif "cross-sectional" in text_lower:
            return "Cross-Sectional Study"
        elif "systematic review" in text_lower:
            return "Systematic Review"
        elif "meta-analysis" in text_lower:
            return "Meta-Analysis"
        else:
            return "Unknown"

    def _extract_sample_size(self, text: str) -> str | None:
        """Extract sample size from methods."""
        patterns = [
            r"n\s*=\s*(\d+)",
            r"(\d+)\s+participants?",
            r"(\d+)\s+subjects?",
            r"(\d+)\s+patients?",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_statistics(self, text: str) -> list[str]:
        """Extract statistical methods mentioned."""
        methods = []

        statistical_terms = [
            "t-test",
            "ANOVA",
            "regression",
            "chi-square",
            "Mann-Whitney",
            "Wilcoxon",
            "Kruskal-Wallis",
            "correlation",
            "logistic regression",
            "Cox regression",
        ]

        text_lower = text.lower()
        for term in statistical_terms:
            if term.lower() in text_lower:
                methods.append(term)

        return methods
