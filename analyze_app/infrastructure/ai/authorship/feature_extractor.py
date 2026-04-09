from __future__ import annotations

import ast
import math
import re
from collections import Counter


class FeatureExtractor:
    """Extract stylometric and structural features for AI-authorship inference."""

    _TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|\S")
    _SNAKE_RE = re.compile(r"^[a-z]+(?:_[a-z0-9]+)+$")
    _KEYWORDS = {
        "def",
        "class",
        "return",
        "if",
        "elif",
        "else",
        "for",
        "while",
        "try",
        "except",
        "with",
        "import",
        "from",
        "lambda",
        "async",
        "await",
    }

    def extract(self, code: str, embedding: list[float] | None = None) -> dict[str, float]:
        lines = code.splitlines()
        line_count = max(len(lines), 1)
        stripped = [line.strip() for line in lines]
        non_empty = [line for line in stripped if line]
        comment_lines = [line for line in stripped if line.startswith("#")]
        blank_lines = [line for line in stripped if not line]

        tokens = self._TOKEN_RE.findall(code)
        token_count = max(len(tokens), 1)
        identifiers = [t for t in tokens if t and (t[0].isalpha() or t[0] == "_")]
        snake_case = [name for name in identifiers if self._SNAKE_RE.match(name)]

        punct_count = sum(1 for t in tokens if not (t[0].isalnum() or t[0] == "_"))
        keyword_count = sum(1 for t in tokens if t in self._KEYWORDS)

        line_lengths = [len(line) for line in non_empty] or [0]
        indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.startswith(" ")]

        repetition = self._repetition_ratio(tokens)
        ast_metrics = self._ast_metrics(code)
        embedding_metrics = self._embedding_metrics(embedding)

        features: dict[str, float] = {
            "line_count": float(line_count),
            "avg_line_length": float(sum(line_lengths) / max(len(line_lengths), 1)),
            "std_line_length": float(self._stddev(line_lengths)),
            "comment_ratio": len(comment_lines) / line_count,
            "blank_ratio": len(blank_lines) / line_count,
            "token_count": float(token_count),
            "avg_token_length": (sum(len(t) for t in tokens) / token_count) if tokens else 0.0,
            "keyword_ratio": keyword_count / token_count,
            "punctuation_ratio": punct_count / token_count,
            "snake_case_ratio": len(snake_case) / max(len(identifiers), 1),
            "avg_indent": float(sum(indents) / max(len(indents), 1)),
            "repetition_ratio": repetition,
            **ast_metrics,
            **embedding_metrics,
        }
        return features

    @staticmethod
    def _stddev(values: list[int]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    @staticmethod
    def _repetition_ratio(tokens: list[str]) -> float:
        if not tokens:
            return 0.0
        counts = Counter(tokens)
        repeated = sum(v - 1 for v in counts.values() if v > 1)
        return repeated / len(tokens)

    def _ast_metrics(self, code: str) -> dict[str, float]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {
                "function_count": 0.0,
                "class_count": 0.0,
                "branch_count": 0.0,
                "comprehension_count": 0.0,
                "ast_depth": 0.0,
                "syntax_error": 1.0,
            }

        function_count = 0
        class_count = 0
        branch_count = 0
        comprehension_count = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1
            elif isinstance(node, ast.ClassDef):
                class_count += 1
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.Match)):
                branch_count += 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                comprehension_count += 1

        return {
            "function_count": float(function_count),
            "class_count": float(class_count),
            "branch_count": float(branch_count),
            "comprehension_count": float(comprehension_count),
            "ast_depth": float(self._max_depth(tree)),
            "syntax_error": 0.0,
        }

    def _max_depth(self, tree: ast.AST) -> int:
        max_depth = 0
        stack: list[tuple[ast.AST, int]] = [(tree, 1)]
        while stack:
            node, depth = stack.pop()
            max_depth = max(max_depth, depth)
            for child in ast.iter_child_nodes(node):
                stack.append((child, depth + 1))
        return max_depth

    @staticmethod
    def _embedding_metrics(embedding: list[float] | None) -> dict[str, float]:
        if not embedding:
            return {
                "embedding_mean": 0.0,
                "embedding_std": 0.0,
                "embedding_l2": 0.0,
                "embedding_dim": 0.0,
            }
        mean = sum(embedding) / len(embedding)
        variance = sum((x - mean) ** 2 for x in embedding) / len(embedding)
        l2 = math.sqrt(sum(x * x for x in embedding))
        return {
            "embedding_mean": float(mean),
            "embedding_std": float(math.sqrt(variance)),
            "embedding_l2": float(l2),
            "embedding_dim": float(len(embedding)),
        }
