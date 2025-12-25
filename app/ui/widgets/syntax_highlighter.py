"""
Syntax highlighter for source code in comparison views.

Provides:
- Multi-language syntax highlighting
- Customizable color schemes
- Diff-aware highlighting
- Line-level and token-level highlighting
- Support for common programming languages
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, List, Tuple, Pattern, Callable

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import (
    QSyntaxHighlighter, QTextDocument, QTextCharFormat,
    QFont, QColor, QBrush, QPalette, QTextBlockUserData
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit


class TokenType(Enum):
    """Types of syntax tokens."""
    KEYWORD = auto()
    KEYWORD_CONSTANT = auto()
    KEYWORD_TYPE = auto()
    KEYWORD_CONTROL = auto()
    KEYWORD_OPERATOR = auto()
    KEYWORD_DECLARATION = auto()
    
    STRING = auto()
    STRING_ESCAPE = auto()
    STRING_INTERPOLATION = auto()
    
    NUMBER = auto()
    NUMBER_FLOAT = auto()
    NUMBER_HEX = auto()
    NUMBER_BINARY = auto()
    NUMBER_OCTAL = auto()
    
    COMMENT = auto()
    COMMENT_DOC = auto()
    COMMENT_TODO = auto()
    
    OPERATOR = auto()
    DELIMITER = auto()
    BRACKET = auto()
    
    FUNCTION = auto()
    FUNCTION_BUILTIN = auto()
    
    CLASS = auto()
    DECORATOR = auto()
    
    VARIABLE = auto()
    VARIABLE_SPECIAL = auto()
    CONSTANT = auto()
    
    PREPROCESSOR = auto()
    MACRO = auto()
    
    TAG = auto()
    ATTRIBUTE = auto()
    
    REGEX = auto()
    
    ERROR = auto()
    DEFAULT = auto()


@dataclass
class HighlightRule:
    """A highlighting rule with pattern and format."""
    pattern: str
    token_type: TokenType
    flags: int = 0
    group: int = 0  # Capture group to highlight
    
    _compiled: Optional[Pattern] = field(default=None, repr=False)
    
    def compile(self) -> Pattern:
        """Compile the pattern."""
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, self.flags)
        return self._compiled


@dataclass
class MultiLineRule:
    """Rule for multi-line constructs like block comments."""
    start_pattern: str
    end_pattern: str
    token_type: TokenType
    escape_char: Optional[str] = None
    state_id: int = 1
    
    _start_compiled: Optional[Pattern] = field(default=None, repr=False)
    _end_compiled: Optional[Pattern] = field(default=None, repr=False)
    
    def compile_start(self) -> Pattern:
        if self._start_compiled is None:
            self._start_compiled = re.compile(self.start_pattern)
        return self._start_compiled
    
    def compile_end(self) -> Pattern:
        if self._end_compiled is None:
            self._end_compiled = re.compile(self.end_pattern)
        return self._end_compiled


@dataclass
class ColorScheme:
    """Color scheme for syntax highlighting."""
    name: str
    background: QColor
    foreground: QColor
    
    # Token colors
    colors: Dict[TokenType, QColor] = field(default_factory=dict)
    
    # Token styles (bold, italic)
    bold: set[TokenType] = field(default_factory=set)
    italic: set[TokenType] = field(default_factory=set)
    underline: set[TokenType] = field(default_factory=set)
    
    def get_format(self, token_type: TokenType) -> QTextCharFormat:
        """Get QTextCharFormat for a token type."""
        fmt = QTextCharFormat()
        
        if token_type in self.colors:
            fmt.setForeground(self.colors[token_type])
        else:
            fmt.setForeground(self.foreground)
        
        if token_type in self.bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        
        if token_type in self.italic:
            fmt.setFontItalic(True)
        
        if token_type in self.underline:
            fmt.setFontUnderline(True)
        
        return fmt


class ColorSchemes:
    """Predefined color schemes."""
    
    @staticmethod
    def default_light() -> ColorScheme:
        """Default light color scheme."""
        return ColorScheme(
            name="Default Light",
            background=QColor(255, 255, 255),
            foreground=QColor(0, 0, 0),
            colors={
                TokenType.KEYWORD: QColor(0, 0, 200),
                TokenType.KEYWORD_CONSTANT: QColor(0, 0, 200),
                TokenType.KEYWORD_TYPE: QColor(0, 128, 128),
                TokenType.KEYWORD_CONTROL: QColor(128, 0, 128),
                TokenType.KEYWORD_DECLARATION: QColor(0, 0, 200),
                
                TokenType.STRING: QColor(163, 21, 21),
                TokenType.STRING_ESCAPE: QColor(200, 100, 0),
                TokenType.STRING_INTERPOLATION: QColor(200, 50, 50),
                
                TokenType.NUMBER: QColor(0, 128, 0),
                TokenType.NUMBER_FLOAT: QColor(0, 128, 0),
                TokenType.NUMBER_HEX: QColor(0, 128, 0),
                
                TokenType.COMMENT: QColor(0, 128, 0),
                TokenType.COMMENT_DOC: QColor(64, 128, 128),
                TokenType.COMMENT_TODO: QColor(200, 100, 0),
                
                TokenType.OPERATOR: QColor(0, 0, 0),
                TokenType.DELIMITER: QColor(0, 0, 0),
                TokenType.BRACKET: QColor(0, 0, 0),
                
                TokenType.FUNCTION: QColor(128, 0, 0),
                TokenType.FUNCTION_BUILTIN: QColor(0, 100, 150),
                
                TokenType.CLASS: QColor(0, 100, 100),
                TokenType.DECORATOR: QColor(128, 64, 0),
                
                TokenType.VARIABLE: QColor(0, 0, 0),
                TokenType.VARIABLE_SPECIAL: QColor(128, 0, 128),
                TokenType.CONSTANT: QColor(0, 100, 0),
                
                TokenType.PREPROCESSOR: QColor(128, 64, 0),
                TokenType.MACRO: QColor(128, 64, 0),
                
                TokenType.TAG: QColor(0, 0, 200),
                TokenType.ATTRIBUTE: QColor(200, 0, 0),
                
                TokenType.REGEX: QColor(200, 100, 0),
                
                TokenType.ERROR: QColor(255, 0, 0),
            },
            bold={
                TokenType.KEYWORD,
                TokenType.KEYWORD_CONSTANT,
                TokenType.KEYWORD_TYPE,
                TokenType.KEYWORD_CONTROL,
                TokenType.KEYWORD_DECLARATION,
            },
            italic={
                TokenType.COMMENT,
                TokenType.COMMENT_DOC,
                TokenType.COMMENT_TODO,
            },
        )
    
    @staticmethod
    def default_dark() -> ColorScheme:
        """Default dark color scheme."""
        return ColorScheme(
            name="Default Dark",
            background=QColor(30, 30, 30),
            foreground=QColor(212, 212, 212),
            colors={
                TokenType.KEYWORD: QColor(86, 156, 214),
                TokenType.KEYWORD_CONSTANT: QColor(86, 156, 214),
                TokenType.KEYWORD_TYPE: QColor(78, 201, 176),
                TokenType.KEYWORD_CONTROL: QColor(197, 134, 192),
                TokenType.KEYWORD_DECLARATION: QColor(86, 156, 214),
                
                TokenType.STRING: QColor(206, 145, 120),
                TokenType.STRING_ESCAPE: QColor(215, 186, 125),
                TokenType.STRING_INTERPOLATION: QColor(220, 160, 100),
                
                TokenType.NUMBER: QColor(181, 206, 168),
                TokenType.NUMBER_FLOAT: QColor(181, 206, 168),
                TokenType.NUMBER_HEX: QColor(181, 206, 168),
                
                TokenType.COMMENT: QColor(106, 153, 85),
                TokenType.COMMENT_DOC: QColor(96, 139, 78),
                TokenType.COMMENT_TODO: QColor(200, 150, 80),
                
                TokenType.OPERATOR: QColor(212, 212, 212),
                TokenType.DELIMITER: QColor(212, 212, 212),
                TokenType.BRACKET: QColor(212, 212, 212),
                
                TokenType.FUNCTION: QColor(220, 220, 170),
                TokenType.FUNCTION_BUILTIN: QColor(200, 200, 150),
                
                TokenType.CLASS: QColor(78, 201, 176),
                TokenType.DECORATOR: QColor(220, 220, 170),
                
                TokenType.VARIABLE: QColor(156, 220, 254),
                TokenType.VARIABLE_SPECIAL: QColor(156, 220, 254),
                TokenType.CONSTANT: QColor(100, 200, 200),
                
                TokenType.PREPROCESSOR: QColor(155, 155, 155),
                TokenType.MACRO: QColor(190, 183, 255),
                
                TokenType.TAG: QColor(86, 156, 214),
                TokenType.ATTRIBUTE: QColor(156, 220, 254),
                
                TokenType.REGEX: QColor(215, 186, 125),
                
                TokenType.ERROR: QColor(244, 71, 71),
            },
            bold={
                TokenType.KEYWORD,
                TokenType.KEYWORD_CONSTANT,
                TokenType.KEYWORD_TYPE,
                TokenType.KEYWORD_CONTROL,
                TokenType.KEYWORD_DECLARATION,
            },
            italic={
                TokenType.COMMENT,
                TokenType.COMMENT_DOC,
                TokenType.COMMENT_TODO,
            },
        )
    
    @staticmethod
    def monokai() -> ColorScheme:
        """Monokai color scheme."""
        return ColorScheme(
            name="Monokai",
            background=QColor(39, 40, 34),
            foreground=QColor(248, 248, 242),
            colors={
                TokenType.KEYWORD: QColor(249, 38, 114),
                TokenType.KEYWORD_CONSTANT: QColor(174, 129, 255),
                TokenType.KEYWORD_TYPE: QColor(102, 217, 239),
                TokenType.KEYWORD_CONTROL: QColor(249, 38, 114),
                TokenType.KEYWORD_DECLARATION: QColor(249, 38, 114),
                
                TokenType.STRING: QColor(230, 219, 116),
                TokenType.STRING_ESCAPE: QColor(174, 129, 255),
                
                TokenType.NUMBER: QColor(174, 129, 255),
                
                TokenType.COMMENT: QColor(117, 113, 94),
                TokenType.COMMENT_DOC: QColor(117, 113, 94),
                
                TokenType.FUNCTION: QColor(166, 226, 46),
                TokenType.CLASS: QColor(102, 217, 239),
                TokenType.DECORATOR: QColor(166, 226, 46),
                
                TokenType.VARIABLE: QColor(248, 248, 242),
                TokenType.CONSTANT: QColor(174, 129, 255),
                
                TokenType.TAG: QColor(249, 38, 114),
                TokenType.ATTRIBUTE: QColor(166, 226, 46),
            },
            bold=set(),
            italic={TokenType.COMMENT, TokenType.COMMENT_DOC},
        )
    
    @staticmethod
    def solarized_light() -> ColorScheme:
        """Solarized Light color scheme."""
        return ColorScheme(
            name="Solarized Light",
            background=QColor(253, 246, 227),
            foreground=QColor(101, 123, 131),
            colors={
                TokenType.KEYWORD: QColor(133, 153, 0),
                TokenType.KEYWORD_CONSTANT: QColor(42, 161, 152),
                TokenType.KEYWORD_TYPE: QColor(181, 137, 0),
                
                TokenType.STRING: QColor(42, 161, 152),
                TokenType.NUMBER: QColor(42, 161, 152),
                
                TokenType.COMMENT: QColor(147, 161, 161),
                
                TokenType.FUNCTION: QColor(38, 139, 210),
                TokenType.CLASS: QColor(181, 137, 0),
                
                TokenType.VARIABLE: QColor(38, 139, 210),
                TokenType.CONSTANT: QColor(203, 75, 22),
                
                TokenType.TAG: QColor(38, 139, 210),
                TokenType.ATTRIBUTE: QColor(181, 137, 0),
            },
            bold={TokenType.KEYWORD},
            italic={TokenType.COMMENT},
        )
    
    @staticmethod
    def github() -> ColorScheme:
        """GitHub-style color scheme."""
        return ColorScheme(
            name="GitHub",
            background=QColor(255, 255, 255),
            foreground=QColor(36, 41, 46),
            colors={
                TokenType.KEYWORD: QColor(215, 58, 73),
                TokenType.KEYWORD_CONSTANT: QColor(0, 92, 197),
                TokenType.KEYWORD_TYPE: QColor(0, 92, 197),
                
                TokenType.STRING: QColor(3, 47, 98),
                TokenType.NUMBER: QColor(0, 92, 197),
                
                TokenType.COMMENT: QColor(106, 115, 125),
                
                TokenType.FUNCTION: QColor(111, 66, 193),
                TokenType.CLASS: QColor(111, 66, 193),
                TokenType.DECORATOR: QColor(227, 98, 9),
                
                TokenType.VARIABLE: QColor(36, 41, 46),
                TokenType.CONSTANT: QColor(0, 92, 197),
                
                TokenType.TAG: QColor(34, 134, 58),
                TokenType.ATTRIBUTE: QColor(111, 66, 193),
            },
            bold={TokenType.KEYWORD},
            italic={TokenType.COMMENT},
        )


class LanguageDefinition:
    """Base class for language definitions."""
    
    name: str = "Unknown"
    file_extensions: List[str] = []
    mime_types: List[str] = []
    
    single_line_rules: List[HighlightRule] = []
    multi_line_rules: List[MultiLineRule] = []
    
    @classmethod
    def get_rules(cls) -> List[HighlightRule]:
        """Get all highlighting rules."""
        return cls.single_line_rules
    
    @classmethod
    def get_multiline_rules(cls) -> List[MultiLineRule]:
        """Get multi-line highlighting rules."""
        return cls.multi_line_rules


class PythonLanguage(LanguageDefinition):
    """Python language definition."""
    
    name = "Python"
    file_extensions = [".py", ".pyw", ".pyi", ".pyx"]
    mime_types = ["text/x-python"]
    
    # Keywords
    KEYWORDS = (
        r'\b(and|as|assert|async|await|break|class|continue|def|del|elif|else|'
        r'except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|'
        r'or|pass|raise|return|try|while|with|yield)\b'
    )
    
    KEYWORD_CONSTANTS = r'\b(True|False|None|Ellipsis|NotImplemented)\b'
    
    BUILTINS = (
        r'\b(abs|all|any|ascii|bin|bool|breakpoint|bytearray|bytes|callable|'
        r'chr|classmethod|compile|complex|delattr|dict|dir|divmod|enumerate|'
        r'eval|exec|filter|float|format|frozenset|getattr|globals|hasattr|'
        r'hash|help|hex|id|input|int|isinstance|issubclass|iter|len|list|'
        r'locals|map|max|memoryview|min|next|object|oct|open|ord|pow|print|'
        r'property|range|repr|reversed|round|set|setattr|slice|sorted|'
        r'staticmethod|str|sum|super|tuple|type|vars|zip|__import__)\b'
    )
    
    single_line_rules = [
        # Comments (before strings to handle # in strings correctly)
        HighlightRule(r'#.*$', TokenType.COMMENT),
        
        # Decorators
        HighlightRule(r'@[\w\.]+', TokenType.DECORATOR),
        
        # Triple-quoted strings (handled specially but mark start)
        HighlightRule(r'[fFrRbBuU]?"""', TokenType.STRING),
        HighlightRule(r"[fFrRbBuU]?'''", TokenType.STRING),
        
        # Strings
        HighlightRule(r'[fFrRbBuU]?"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r"[fFrRbBuU]?'[^'\\]*(\\.[^'\\]*)*'", TokenType.STRING),
        
        # f-string interpolation
        HighlightRule(r'\{[^}]*\}', TokenType.STRING_INTERPOLATION),
        
        # Numbers
        HighlightRule(r'\b0[xX][0-9a-fA-F_]+\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0[oO][0-7_]+\b', TokenType.NUMBER_OCTAL),
        HighlightRule(r'\b0[bB][01_]+\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b\d+\.?\d*([eE][+-]?\d+)?[jJ]?\b', TokenType.NUMBER_FLOAT),
        HighlightRule(r'\b\d+[jJ]?\b', TokenType.NUMBER),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(KEYWORD_CONSTANTS, TokenType.KEYWORD_CONSTANT),
        
        # Built-in functions
        HighlightRule(BUILTINS, TokenType.FUNCTION_BUILTIN),
        
        # Function definitions
        HighlightRule(r'\bdef\s+(\w+)', TokenType.FUNCTION, group=1),
        
        # Class definitions
        HighlightRule(r'\bclass\s+(\w+)', TokenType.CLASS, group=1),
        
        # Function calls
        HighlightRule(r'\b(\w+)\s*\(', TokenType.FUNCTION, group=1),
        
        # Special variables
        HighlightRule(r'\b(self|cls)\b', TokenType.VARIABLE_SPECIAL),
        HighlightRule(r'\b__\w+__\b', TokenType.VARIABLE_SPECIAL),
        
        # Type hints
        HighlightRule(r'->\s*(\w+)', TokenType.KEYWORD_TYPE, group=1),
        HighlightRule(r':\s*(\w+)(?:\s*=)?', TokenType.KEYWORD_TYPE, group=1),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'"""', r'"""', TokenType.STRING, state_id=1),
        MultiLineRule(r"'''", r"'''", TokenType.STRING, state_id=2),
    ]


class JavaScriptLanguage(LanguageDefinition):
    """JavaScript/TypeScript language definition."""
    
    name = "JavaScript"
    file_extensions = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
    mime_types = ["text/javascript", "application/javascript"]
    
    KEYWORDS = (
        r'\b(async|await|break|case|catch|class|const|continue|debugger|default|'
        r'delete|do|else|export|extends|finally|for|function|if|import|in|'
        r'instanceof|let|new|of|return|static|super|switch|this|throw|try|'
        r'typeof|var|void|while|with|yield|enum|implements|interface|package|'
        r'private|protected|public|abstract|as|constructor|declare|from|get|'
        r'is|module|namespace|require|set|type|readonly|keyof|infer)\b'
    )
    
    KEYWORD_CONSTANTS = r'\b(true|false|null|undefined|NaN|Infinity)\b'
    
    TYPES = (
        r'\b(any|boolean|never|number|object|string|symbol|unknown|void|'
        r'bigint|Array|Boolean|Date|Error|Function|Map|Number|Object|Promise|'
        r'RegExp|Set|String|Symbol|WeakMap|WeakSet)\b'
    )
    
    single_line_rules = [
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),
        
        # JSDoc
        HighlightRule(r'/\*\*.*?\*/', TokenType.COMMENT_DOC),
        
        # Template strings
        HighlightRule(r'`[^`\\]*(\\.[^`\\]*)*`', TokenType.STRING),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r"'[^'\\]*(\\.[^'\\]*)*'", TokenType.STRING),
        
        # Template string interpolation
        HighlightRule(r'\$\{[^}]*\}', TokenType.STRING_INTERPOLATION),
        
        # Regex
        HighlightRule(r'/(?![/*])(?:[^\\/\n]|\\.)+/[gimsuvy]*', TokenType.REGEX),
        
        # Numbers
        HighlightRule(r'\b0[xX][0-9a-fA-F_]+n?\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0[oO][0-7_]+n?\b', TokenType.NUMBER_OCTAL),
        HighlightRule(r'\b0[bB][01_]+n?\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b\d+\.?\d*([eE][+-]?\d+)?n?\b', TokenType.NUMBER_FLOAT),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(KEYWORD_CONSTANTS, TokenType.KEYWORD_CONSTANT),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE),
        
        # Decorators (TypeScript)
        HighlightRule(r'@[\w]+', TokenType.DECORATOR),
        
        # Function definitions
        HighlightRule(r'\bfunction\s+(\w+)', TokenType.FUNCTION, group=1),
        HighlightRule(r'(\w+)\s*[=:]\s*(?:async\s*)?\(', TokenType.FUNCTION, group=1),
        HighlightRule(r'(\w+)\s*[=:]\s*(?:async\s*)?function', TokenType.FUNCTION, group=1),
        
        # Class definitions
        HighlightRule(r'\bclass\s+(\w+)', TokenType.CLASS, group=1),
        
        # Arrow functions
        HighlightRule(r'=>', TokenType.OPERATOR),
        
        # Special
        HighlightRule(r'\bthis\b', TokenType.VARIABLE_SPECIAL),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class CppLanguage(LanguageDefinition):
    """C/C++ language definition."""
    
    name = "C++"
    file_extensions = [".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".c++", ".h++"]
    mime_types = ["text/x-c", "text/x-c++"]
    
    KEYWORDS = (
        r'\b(alignas|alignof|and|and_eq|asm|auto|bitand|bitor|break|case|'
        r'catch|class|compl|concept|const|consteval|constexpr|constinit|'
        r'const_cast|continue|co_await|co_return|co_yield|decltype|default|'
        r'delete|do|dynamic_cast|else|enum|explicit|export|extern|final|for|'
        r'friend|goto|if|inline|mutable|namespace|new|noexcept|not|not_eq|'
        r'nullptr|operator|or|or_eq|override|private|protected|public|'
        r'register|reinterpret_cast|requires|return|sizeof|static|'
        r'static_assert|static_cast|struct|switch|template|this|thread_local|'
        r'throw|try|typedef|typeid|typename|union|using|virtual|volatile|'
        r'while|xor|xor_eq)\b'
    )
    
    TYPES = (
        r'\b(bool|char|char8_t|char16_t|char32_t|double|float|int|long|short|'
        r'signed|unsigned|void|wchar_t|int8_t|int16_t|int32_t|int64_t|'
        r'uint8_t|uint16_t|uint32_t|uint64_t|size_t|ptrdiff_t|nullptr_t|'
        r'string|vector|map|set|list|array|deque|queue|stack|pair|tuple)\b'
    )
    
    CONSTANTS = r'\b(true|false|NULL|nullptr|EOF)\b'
    
    single_line_rules = [
        # Preprocessor
        HighlightRule(r'^\s*#\s*\w+', TokenType.PREPROCESSOR),
        HighlightRule(r'^\s*#\s*include\s*[<"][^>"]+[>"]', TokenType.PREPROCESSOR),
        
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r"'[^'\\]*(\\.[^'\\]*)*'", TokenType.STRING),
        
        # Raw strings (C++11)
        HighlightRule(r'R"[^(]*\([^)]*\)[^"]*"', TokenType.STRING),
        
        # Character literals
        HighlightRule(r"'\\?.'", TokenType.STRING),
        
        # Numbers
        HighlightRule(r'\b0[xX][0-9a-fA-F\']+[uUlL]*\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0[bB][01\']+[uUlL]*\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b0[0-7\']+[uUlL]*\b', TokenType.NUMBER_OCTAL),
        HighlightRule(r'\b\d+\.?\d*([eE][+-]?\d+)?[fFlL]?\b', TokenType.NUMBER_FLOAT),
        HighlightRule(r'\b\d+[uUlL]*\b', TokenType.NUMBER),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE),
        HighlightRule(CONSTANTS, TokenType.KEYWORD_CONSTANT),
        
        # Macros (UPPERCASE_IDENTIFIERS)
        HighlightRule(r'\b[A-Z][A-Z0-9_]+\b', TokenType.MACRO),
        
        # Function definitions
        HighlightRule(r'\b(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*\{', 
                     TokenType.FUNCTION, group=1),
        
        # Class/struct definitions
        HighlightRule(r'\b(?:class|struct)\s+(\w+)', TokenType.CLASS, group=1),
        
        # Namespace
        HighlightRule(r'\bnamespace\s+(\w+)', TokenType.CLASS, group=1),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class JavaLanguage(LanguageDefinition):
    """Java language definition."""
    
    name = "Java"
    file_extensions = [".java"]
    mime_types = ["text/x-java"]
    
    KEYWORDS = (
        r'\b(abstract|assert|break|case|catch|class|const|continue|default|'
        r'do|else|enum|extends|final|finally|for|goto|if|implements|import|'
        r'instanceof|interface|native|new|package|private|protected|public|'
        r'return|static|strictfp|super|switch|synchronized|this|throw|throws|'
        r'transient|try|volatile|while|var|yield|record|sealed|permits|'
        r'non-sealed)\b'
    )
    
    TYPES = (
        r'\b(boolean|byte|char|double|float|int|long|short|void|'
        r'String|Integer|Long|Double|Float|Boolean|Byte|Short|Character|'
        r'Object|Class|Void|Number|Enum|Throwable|Exception|Error|'
        r'List|ArrayList|LinkedList|Map|HashMap|TreeMap|Set|HashSet|TreeSet|'
        r'Queue|Deque|Stack|Vector|Collection|Iterator|Iterable|Comparable|'
        r'Comparator|Optional|Stream)\b'
    )
    
    CONSTANTS = r'\b(true|false|null)\b'
    
    single_line_rules = [
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),
        
        # Annotations
        HighlightRule(r'@\w+', TokenType.DECORATOR),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        
        # Text blocks (Java 15+)
        HighlightRule(r'"""', TokenType.STRING),
        
        # Character literals
        HighlightRule(r"'\\?.'", TokenType.STRING),
        
        # Numbers
        HighlightRule(r'\b0[xX][0-9a-fA-F_]+[lL]?\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0[bB][01_]+[lL]?\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b\d+\.?\d*([eE][+-]?\d+)?[fFdDlL]?\b', TokenType.NUMBER_FLOAT),
        HighlightRule(r'\b\d+[lL]?\b', TokenType.NUMBER),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE),
        HighlightRule(CONSTANTS, TokenType.KEYWORD_CONSTANT),
        
        # Package/import
        HighlightRule(r'\b(package|import)\s+([\w.]+)', TokenType.KEYWORD),
        
        # Class/interface definitions
        HighlightRule(r'\b(?:class|interface|enum|record)\s+(\w+)', 
                     TokenType.CLASS, group=1),
        
        # Method definitions
        HighlightRule(r'\b(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{', 
                     TokenType.FUNCTION, group=1),
        
        # Constants (UPPERCASE)
        HighlightRule(r'\b[A-Z][A-Z0-9_]+\b', TokenType.CONSTANT),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*\*', r'\*/', TokenType.COMMENT_DOC, state_id=1),
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=2),
        MultiLineRule(r'"""', r'"""', TokenType.STRING, state_id=3),
    ]


class HtmlLanguage(LanguageDefinition):
    """HTML/XML language definition."""
    
    name = "HTML"
    file_extensions = [".html", ".htm", ".xhtml", ".xml", ".svg"]
    mime_types = ["text/html", "text/xml", "application/xml"]
    
    single_line_rules = [
        # Comments
        HighlightRule(r'<!--.*?-->', TokenType.COMMENT),
        
        # DOCTYPE
        HighlightRule(r'<!DOCTYPE[^>]*>', TokenType.PREPROCESSOR),
        
        # CDATA
        HighlightRule(r'<!\[CDATA\[.*?\]\]>', TokenType.STRING),
        
        # Processing instructions
        HighlightRule(r'<\?.*?\?>', TokenType.PREPROCESSOR),
        
        # Tags
        HighlightRule(r'</?\s*\w+', TokenType.TAG),
        HighlightRule(r'/?\s*>', TokenType.TAG),
        
        # Attributes
        HighlightRule(r'\b(\w+)\s*=', TokenType.ATTRIBUTE, group=1),
        
        # Attribute values
        HighlightRule(r'"[^"]*"', TokenType.STRING),
        HighlightRule(r"'[^']*'", TokenType.STRING),
        
        # Entities
        HighlightRule(r'&\w+;', TokenType.STRING_ESCAPE),
        HighlightRule(r'&#\d+;', TokenType.STRING_ESCAPE),
        HighlightRule(r'&#x[0-9a-fA-F]+;', TokenType.STRING_ESCAPE),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'<!--', r'-->', TokenType.COMMENT, state_id=1),
    ]


class CssLanguage(LanguageDefinition):
    """CSS language definition."""
    
    name = "CSS"
    file_extensions = [".css", ".scss", ".sass", ".less"]
    mime_types = ["text/css"]
    
    single_line_rules = [
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),  # SCSS/Less
        
        # Selectors
        HighlightRule(r'[.#][\w-]+', TokenType.CLASS),
        HighlightRule(r'\[[\w-]+\]', TokenType.ATTRIBUTE),
        HighlightRule(r':[\w-]+', TokenType.KEYWORD),
        HighlightRule(r'::[\w-]+', TokenType.KEYWORD),
        
        # Properties
        HighlightRule(r'[\w-]+\s*:', TokenType.ATTRIBUTE),
        
        # At-rules
        HighlightRule(r'@[\w-]+', TokenType.KEYWORD),
        
        # Colors
        HighlightRule(r'#[0-9a-fA-F]{3,8}\b', TokenType.NUMBER_HEX),
        
        # Numbers with units
        HighlightRule(r'\b\d+\.?\d*(px|em|rem|%|vh|vw|vmin|vmax|ch|ex|cm|mm|in|pt|pc|deg|rad|grad|turn|s|ms|Hz|kHz|dpi|dpcm|dppx)?\b', 
                     TokenType.NUMBER),
        
        # Strings
        HighlightRule(r'"[^"]*"', TokenType.STRING),
        HighlightRule(r"'[^']*'", TokenType.STRING),
        
        # URLs
        HighlightRule(r'url\([^)]*\)', TokenType.STRING),
        
        # Variables (SCSS/CSS custom properties)
        HighlightRule(r'\$[\w-]+', TokenType.VARIABLE),
        HighlightRule(r'--[\w-]+', TokenType.VARIABLE),
        HighlightRule(r'var\(--[\w-]+\)', TokenType.VARIABLE),
        
        # Functions
        HighlightRule(r'\b(rgb|rgba|hsl|hsla|calc|min|max|clamp|var)\s*\(', 
                     TokenType.FUNCTION),
        
        # Important
        HighlightRule(r'!important', TokenType.KEYWORD),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class JsonLanguage(LanguageDefinition):
    """JSON language definition."""
    
    name = "JSON"
    file_extensions = [".json", ".jsonc", ".json5"]
    mime_types = ["application/json"]
    
    single_line_rules = [
        # Comments (JSON5/JSONC)
        HighlightRule(r'//.*$', TokenType.COMMENT),
        
        # Strings (keys and values)
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        
        # Numbers
        HighlightRule(r'-?\b\d+\.?\d*([eE][+-]?\d+)?\b', TokenType.NUMBER),
        
        # Constants
        HighlightRule(r'\b(true|false|null)\b', TokenType.KEYWORD_CONSTANT),
        
        # Property names (before colon)
        HighlightRule(r'"[^"]+"\s*:', TokenType.ATTRIBUTE),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class SqlLanguage(LanguageDefinition):
    """SQL language definition."""
    
    name = "SQL"
    file_extensions = [".sql"]
    mime_types = ["application/sql", "text/x-sql"]
    
    KEYWORDS = (
        r'\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|BETWEEN|LIKE|IS|NULL|AS|'
        r'JOIN|INNER|LEFT|RIGHT|OUTER|FULL|CROSS|ON|UNION|ALL|DISTINCT|'
        r'INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|VIEW|INDEX|'
        r'DROP|ALTER|ADD|COLUMN|PRIMARY|KEY|FOREIGN|REFERENCES|CONSTRAINT|'
        r'UNIQUE|CHECK|DEFAULT|AUTO_INCREMENT|CASCADE|ORDER|BY|ASC|DESC|'
        r'GROUP|HAVING|LIMIT|OFFSET|TOP|CASE|WHEN|THEN|ELSE|END|EXISTS|'
        r'GRANT|REVOKE|COMMIT|ROLLBACK|TRANSACTION|BEGIN|DECLARE|CURSOR|'
        r'FETCH|OPEN|CLOSE|PROCEDURE|FUNCTION|TRIGGER|DATABASE|SCHEMA|'
        r'IF|WHILE|LOOP|FOR|RETURN|RETURNS|TEMPORARY|TEMP|WITH|RECURSIVE)\b'
    )
    
    TYPES = (
        r'\b(INT|INTEGER|SMALLINT|BIGINT|DECIMAL|NUMERIC|FLOAT|REAL|DOUBLE|'
        r'CHAR|VARCHAR|TEXT|NCHAR|NVARCHAR|NTEXT|BINARY|VARBINARY|BLOB|'
        r'DATE|TIME|DATETIME|TIMESTAMP|YEAR|BOOLEAN|BOOL|BIT|SERIAL|'
        r'JSON|XML|UUID|ARRAY|MONEY|INTERVAL)\b'
    )
    
    FUNCTIONS = (
        r'\b(COUNT|SUM|AVG|MIN|MAX|COALESCE|NULLIF|CAST|CONVERT|'
        r'UPPER|LOWER|TRIM|LTRIM|RTRIM|SUBSTRING|REPLACE|CONCAT|'
        r'LENGTH|LEN|ROUND|FLOOR|CEIL|ABS|NOW|GETDATE|CURRENT_DATE|'
        r'CURRENT_TIME|CURRENT_TIMESTAMP|EXTRACT|DATEPART|DATEDIFF)\b'
    )
    
    single_line_rules = [
        # Comments
        HighlightRule(r'--.*$', TokenType.COMMENT),
        
        # Strings
        HighlightRule(r"'[^']*'", TokenType.STRING),
        HighlightRule(r'"[^"]*"', TokenType.STRING),
        
        # Numbers
        HighlightRule(r'\b\d+\.?\d*\b', TokenType.NUMBER),
        
        # Keywords (case-insensitive)
        HighlightRule(KEYWORDS, TokenType.KEYWORD, flags=re.IGNORECASE),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE, flags=re.IGNORECASE),
        HighlightRule(FUNCTIONS, TokenType.FUNCTION_BUILTIN, flags=re.IGNORECASE),
        
        # Parameters
        HighlightRule(r'@\w+', TokenType.VARIABLE),
        HighlightRule(r':\w+', TokenType.VARIABLE),
        HighlightRule(r'\$\d+', TokenType.VARIABLE),
        
        # Operators
        HighlightRule(r'[<>=!]+', TokenType.OPERATOR),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class MarkdownLanguage(LanguageDefinition):
    """Markdown language definition."""
    
    name = "Markdown"
    file_extensions = [".md", ".markdown", ".mdown", ".mkd"]
    mime_types = ["text/markdown"]
    
    single_line_rules = [
        # Headers
        HighlightRule(r'^#{1,6}\s.*$', TokenType.KEYWORD, flags=re.MULTILINE),
        
        # Bold
        HighlightRule(r'\*\*[^*]+\*\*', TokenType.KEYWORD),
        HighlightRule(r'__[^_]+__', TokenType.KEYWORD),
        
        # Italic
        HighlightRule(r'\*[^*]+\*', TokenType.STRING),
        HighlightRule(r'_[^_]+_', TokenType.STRING),
        
        # Code spans
        HighlightRule(r'`[^`]+`', TokenType.STRING),
        
        # Links
        HighlightRule(r'\[([^\]]+)\]\([^)]+\)', TokenType.FUNCTION),
        HighlightRule(r'\[([^\]]+)\]\[[^\]]*\]', TokenType.FUNCTION),
        
        # Images
        HighlightRule(r'!\[([^\]]*)\]\([^)]+\)', TokenType.TAG),
        
        # Blockquotes
        HighlightRule(r'^>\s.*$', TokenType.COMMENT, flags=re.MULTILINE),
        
        # Lists
        HighlightRule(r'^\s*[-*+]\s', TokenType.KEYWORD, flags=re.MULTILINE),
        HighlightRule(r'^\s*\d+\.\s', TokenType.KEYWORD, flags=re.MULTILINE),
        
        # Horizontal rules
        HighlightRule(r'^[-*_]{3,}\s*$', TokenType.KEYWORD, flags=re.MULTILINE),
        
        # URLs
        HighlightRule(r'https?://[^\s]+', TokenType.STRING),
        
        # HTML tags
        HighlightRule(r'<[^>]+>', TokenType.TAG),
    ]
    
    multi_line_rules = [
        # Fenced code blocks
        MultiLineRule(r'```', r'```', TokenType.STRING, state_id=1),
    ]


class ShellLanguage(LanguageDefinition):
    """Shell/Bash language definition."""
    
    name = "Shell"
    file_extensions = [".sh", ".bash", ".zsh", ".fish", ".ksh"]
    mime_types = ["application/x-sh", "text/x-shellscript"]
    
    KEYWORDS = (
        r'\b(if|then|else|elif|fi|case|esac|for|while|until|do|done|'
        r'in|function|select|time|coproc|break|continue|return|exit|'
        r'source|alias|unalias|export|readonly|declare|local|typeset|'
        r'shift|set|unset|trap|wait|eval|exec|true|false)\b'
    )
    
    BUILTINS = (
        r'\b(echo|printf|read|cd|pwd|pushd|popd|dirs|let|test|'
        r'type|hash|bind|builtin|caller|command|compgen|complete|'
        r'enable|help|history|jobs|kill|logout|mapfile|readarray|'
        r'suspend|ulimit|umask|getopts|shopt)\b'
    )
    
    single_line_rules = [
        # Shebang
        HighlightRule(r'^#!.*$', TokenType.PREPROCESSOR, flags=re.MULTILINE),
        
        # Comments
        HighlightRule(r'#.*$', TokenType.COMMENT),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r"'[^']*'", TokenType.STRING),
        
        # Command substitution
        HighlightRule(r'\$\([^)]*\)', TokenType.STRING_INTERPOLATION),
        HighlightRule(r'`[^`]*`', TokenType.STRING_INTERPOLATION),
        
        # Variables
        HighlightRule(r'\$\{[^}]+\}', TokenType.VARIABLE),
        HighlightRule(r'\$[a-zA-Z_][a-zA-Z0-9_]*', TokenType.VARIABLE),
        HighlightRule(r'\$[@*#?$!0-9-]', TokenType.VARIABLE_SPECIAL),
        
        # Numbers
        HighlightRule(r'\b\d+\b', TokenType.NUMBER),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(BUILTINS, TokenType.FUNCTION_BUILTIN),
        
        # Function definitions
        HighlightRule(r'\b(\w+)\s*\(\s*\)', TokenType.FUNCTION, group=1),
        HighlightRule(r'\bfunction\s+(\w+)', TokenType.FUNCTION, group=1),
        
        # Redirection
        HighlightRule(r'[<>]{1,2}|&>', TokenType.OPERATOR),
        
        # Pipes
        HighlightRule(r'\|{1,2}', TokenType.OPERATOR),
        HighlightRule(r'&&', TokenType.OPERATOR),
    ]
    
    multi_line_rules = [
        # Here documents
        MultiLineRule(r'<<\s*(\w+)', r'\1', TokenType.STRING, state_id=1),
    ]


class RustLanguage(LanguageDefinition):
    """Rust language definition."""
    
    name = "Rust"
    file_extensions = [".rs"]
    mime_types = ["text/x-rust"]
    
    KEYWORDS = (
        r'\b(as|async|await|break|const|continue|crate|dyn|else|enum|'
        r'extern|false|fn|for|if|impl|in|let|loop|match|mod|move|mut|'
        r'pub|ref|return|self|Self|static|struct|super|trait|true|type|'
        r'unsafe|use|where|while|abstract|become|box|do|final|macro|'
        r'override|priv|try|typeof|unsized|virtual|yield)\b'
    )
    
    TYPES = (
        r'\b(bool|char|str|u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|'
        r'isize|f32|f64|String|Vec|Box|Rc|Arc|Cell|RefCell|Option|Result|'
        r'HashMap|HashSet|BTreeMap|BTreeSet|VecDeque|LinkedList|'
        r'Path|PathBuf|OsStr|OsString|Cow|Pin|Waker|Context)\b'
    )
    
    single_line_rules = [
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),
        HighlightRule(r'///.*$', TokenType.COMMENT_DOC),
        HighlightRule(r'//!.*$', TokenType.COMMENT_DOC),
        
        # Attributes
        HighlightRule(r'#!\?\[.*?\]', TokenType.DECORATOR),
        HighlightRule(r'#\[.*?\]', TokenType.DECORATOR),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r'r#*".*?"#*', TokenType.STRING),  # Raw strings
        HighlightRule(r"b?'[^'\\]*(\\.[^'\\]*)*'", TokenType.STRING),  # Char/byte
        
        # Numbers
        HighlightRule(r'\b0x[0-9a-fA-F_]+\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0o[0-7_]+\b', TokenType.NUMBER_OCTAL),
        HighlightRule(r'\b0b[01_]+\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b\d[\d_]*\.[\d_]*([eE][+-]?[\d_]+)?f?(32|64)?\b', TokenType.NUMBER_FLOAT),
        HighlightRule(r'\b\d[\d_]*(u|i)?(8|16|32|64|128|size)?\b', TokenType.NUMBER),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE),
        
        # Lifetimes
        HighlightRule(r"'[a-zA-Z_]\w*", TokenType.VARIABLE_SPECIAL),
        
        # Macros
        HighlightRule(r'\b\w+!', TokenType.MACRO),
        
        # Function definitions
        HighlightRule(r'\bfn\s+(\w+)', TokenType.FUNCTION, group=1),
        
        # Struct/enum definitions
        HighlightRule(r'\b(?:struct|enum|trait)\s+(\w+)', TokenType.CLASS, group=1),
        
        # Module/use
        HighlightRule(r'\b(?:mod|use)\s+([\w:]+)', TokenType.KEYWORD),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class GoLanguage(LanguageDefinition):
    """Go language definition."""
    
    name = "Go"
    file_extensions = [".go"]
    mime_types = ["text/x-go"]
    
    KEYWORDS = (
        r'\b(break|case|chan|const|continue|default|defer|else|fallthrough|'
        r'for|func|go|goto|if|import|interface|map|package|range|return|'
        r'select|struct|switch|type|var)\b'
    )
    
    TYPES = (
        r'\b(bool|byte|complex64|complex128|error|float32|float64|int|int8|'
        r'int16|int32|int64|rune|string|uint|uint8|uint16|uint32|uint64|'
        r'uintptr|any|comparable)\b'
    )
    
    BUILTINS = (
        r'\b(append|cap|close|complex|copy|delete|imag|len|make|new|panic|'
        r'print|println|real|recover)\b'
    )
    
    CONSTANTS = r'\b(true|false|nil|iota)\b'
    
    single_line_rules = [
        # Comments
        HighlightRule(r'//.*$', TokenType.COMMENT),
        
        # Strings
        HighlightRule(r'"[^"\\]*(\\.[^"\\]*)*"', TokenType.STRING),
        HighlightRule(r'`[^`]*`', TokenType.STRING),  # Raw strings
        HighlightRule(r"'[^'\\]*(\\.[^'\\]*)*'", TokenType.STRING),  # Rune
        
        # Numbers
        HighlightRule(r'\b0[xX][0-9a-fA-F_]+\b', TokenType.NUMBER_HEX),
        HighlightRule(r'\b0[oO][0-7_]+\b', TokenType.NUMBER_OCTAL),
        HighlightRule(r'\b0[bB][01_]+\b', TokenType.NUMBER_BINARY),
        HighlightRule(r'\b\d+\.?\d*([eE][+-]?\d+)?i?\b', TokenType.NUMBER_FLOAT),
        
        # Keywords
        HighlightRule(KEYWORDS, TokenType.KEYWORD),
        HighlightRule(TYPES, TokenType.KEYWORD_TYPE),
        HighlightRule(BUILTINS, TokenType.FUNCTION_BUILTIN),
        HighlightRule(CONSTANTS, TokenType.KEYWORD_CONSTANT),
        
        # Function definitions
        HighlightRule(r'\bfunc\s+(?:\([^)]*\)\s*)?(\w+)', TokenType.FUNCTION, group=1),
        
        # Type definitions
        HighlightRule(r'\btype\s+(\w+)', TokenType.CLASS, group=1),
        
        # Package/import
        HighlightRule(r'\bpackage\s+(\w+)', TokenType.KEYWORD),
    ]
    
    multi_line_rules = [
        MultiLineRule(r'/\*', r'\*/', TokenType.COMMENT, state_id=1),
    ]


class LanguageRegistry:
    """Registry of available language definitions."""
    
    _languages: Dict[str, type] = {
        'python': PythonLanguage,
        'javascript': JavaScriptLanguage,
        'typescript': JavaScriptLanguage,
        'cpp': CppLanguage,
        'c': CppLanguage,
        'java': JavaLanguage,
        'html': HtmlLanguage,
        'xml': HtmlLanguage,
        'css': CssLanguage,
        'scss': CssLanguage,
        'json': JsonLanguage,
        'sql': SqlLanguage,
        'markdown': MarkdownLanguage,
        'shell': ShellLanguage,
        'bash': ShellLanguage,
        'rust': RustLanguage,
        'go': GoLanguage,
    }
    
    _extension_map: Dict[str, str] = {}
    
    @classmethod
    def _build_extension_map(cls) -> None:
        """Build extension to language mapping."""
        if cls._extension_map:
            return
        
        for name, lang_class in cls._languages.items():
            for ext in lang_class.file_extensions:
                cls._extension_map[ext.lower()] = name
    
    @classmethod
    def get_language(cls, name: str) -> Optional[type]:
        """Get language definition by name."""
        return cls._languages.get(name.lower())
    
    @classmethod
    def get_language_for_file(cls, filename: str) -> Optional[type]:
        """Get language definition for a file based on extension."""
        cls._build_extension_map()
        
        # Get extension
        import os
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        lang_name = cls._extension_map.get(ext)
        if lang_name:
            return cls._languages.get(lang_name)
        
        return None
    
    @classmethod
    def register_language(cls, name: str, language_class: type) -> None:
        """Register a new language definition."""
        cls._languages[name.lower()] = language_class
        
        # Update extension map
        for ext in language_class.file_extensions:
            cls._extension_map[ext.lower()] = name.lower()
    
    @classmethod
    def get_all_languages(cls) -> List[str]:
        """Get list of all registered language names."""
        return list(cls._languages.keys())
    
    @classmethod
    def get_all_extensions(cls) -> List[str]:
        """Get list of all supported file extensions."""
        cls._build_extension_map()
        return list(cls._extension_map.keys())


class BlockUserData(QTextBlockUserData):
    """User data attached to text blocks for state tracking."""
    
    def __init__(self):
        super().__init__()
        self.folding_level = 0
        self.is_folded = False
        self.tokens: List[Tuple[int, int, TokenType]] = []  # (start, length, type)


class SyntaxHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for source code.
    
    Supports multiple languages and color schemes.
    """
    
    def __init__(
        self,
        document: QTextDocument,
        language: Optional[str] = None,
        color_scheme: Optional[ColorScheme] = None
    ):
        super().__init__(document)
        
        self._language: Optional[type] = None
        self._color_scheme = color_scheme or ColorSchemes.default_light()
        self._formats: Dict[TokenType, QTextCharFormat] = {}
        self._rules: List[HighlightRule] = []
        self._multiline_rules: List[MultiLineRule] = []
        self._enabled = True
        
        # Build formats
        self._build_formats()
        
        # Set language
        if language:
            self.set_language(language)
    
    def _build_formats(self) -> None:
        """Build text formats from color scheme."""
        self._formats.clear()
        
        for token_type in TokenType:
            self._formats[token_type] = self._color_scheme.get_format(token_type)
    
    def set_language(self, language: str) -> None:
        """Set the language for highlighting."""
        lang_class = LanguageRegistry.get_language(language)
        
        if lang_class:
            self._language = lang_class
            self._rules = [HighlightRule(
                pattern=r.pattern,
                token_type=r.token_type,
                flags=r.flags,
                group=r.group
            ) for r in lang_class.get_rules()]
            self._multiline_rules = lang_class.get_multiline_rules()
            
            # Compile patterns
            for rule in self._rules:
                rule.compile()
            for rule in self._multiline_rules:
                rule.compile_start()
                rule.compile_end()
        else:
            self._language = None
            self._rules = []
            self._multiline_rules = []
        
        self.rehighlight()
    
    def set_language_for_file(self, filename: str) -> bool:
        """Set language based on file extension."""
        lang_class = LanguageRegistry.get_language_for_file(filename)
        
        if lang_class:
            # Find language name
            for name, cls in LanguageRegistry._languages.items():
                if cls == lang_class:
                    self.set_language(name)
                    return True
        
        self._language = None
        self._rules = []
        self._multiline_rules = []
        self.rehighlight()
        return False
    
    def set_color_scheme(self, scheme: ColorScheme) -> None:
        """Set the color scheme."""
        self._color_scheme = scheme
        self._build_formats()
        self.rehighlight()
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable highlighting."""
        self._enabled = enabled
        self.rehighlight()
    
    def highlightBlock(self, text: str) -> None:
        """Highlight a block of text."""
        if not self._enabled or not self._language:
            return
        
        # Create user data for the block
        user_data = BlockUserData()
        
        # Apply single-line rules
        for rule in self._rules:
            pattern = rule.compile()
            
            for match in pattern.finditer(text):
                if rule.group > 0 and rule.group <= len(match.groups()):
                    start = match.start(rule.group)
                    length = len(match.group(rule.group))
                else:
                    start = match.start()
                    length = len(match.group())
                
                fmt = self._formats.get(rule.token_type)
                if fmt:
                    self.setFormat(start, length, fmt)
                    user_data.tokens.append((start, length, rule.token_type))
        
        # Handle multi-line constructs
        self._handle_multiline(text, user_data)
        
        self.setCurrentBlockUserData(user_data)
    
    def _handle_multiline(self, text: str, user_data: BlockUserData) -> None:
        """Handle multi-line highlighting (comments, strings)."""
        if not self._multiline_rules:
            self.setCurrentBlockState(0)
            return
        
        prev_state = self.previousBlockState()
        if prev_state < 0:
            prev_state = 0
        
        start_index = 0
        current_state = prev_state
        
        # If we're continuing a multi-line construct
        if current_state > 0:
            # Find which rule we're in
            for rule in self._multiline_rules:
                if rule.state_id == current_state:
                    # Look for end pattern
                    end_pattern = rule.compile_end()
                    match = end_pattern.search(text)
                    
                    if match:
                        # Found end - highlight up to and including end
                        length = match.end()
                        fmt = self._formats.get(rule.token_type)
                        if fmt:
                            self.setFormat(0, length, fmt)
                        start_index = match.end()
                        current_state = 0
                    else:
                        # Still in multi-line - highlight entire line
                        fmt = self._formats.get(rule.token_type)
                        if fmt:
                            self.setFormat(0, len(text), fmt)
                        self.setCurrentBlockState(current_state)
                        return
                    break
        
        # Look for new multi-line constructs
        while start_index < len(text):
            earliest_match = None
            earliest_rule = None
            earliest_pos = len(text)
            
            for rule in self._multiline_rules:
                start_pattern = rule.compile_start()
                match = start_pattern.search(text, start_index)
                
                if match and match.start() < earliest_pos:
                    earliest_match = match
                    earliest_rule = rule
                    earliest_pos = match.start()
            
            if earliest_match is None:
                break
            
            # Found a start - look for end
            end_pattern = earliest_rule.compile_end()
            end_match = end_pattern.search(text, earliest_match.end())
            
            if end_match:
                # Complete construct on this line
                length = end_match.end() - earliest_match.start()
                fmt = self._formats.get(earliest_rule.token_type)
                if fmt:
                    self.setFormat(earliest_match.start(), length, fmt)
                start_index = end_match.end()
            else:
                # Construct continues to next line
                length = len(text) - earliest_match.start()
                fmt = self._formats.get(earliest_rule.token_type)
                if fmt:
                    self.setFormat(earliest_match.start(), length, fmt)
                self.setCurrentBlockState(earliest_rule.state_id)
                return
        
        self.setCurrentBlockState(0)
    
    def get_language_name(self) -> Optional[str]:
        """Get the current language name."""
        if self._language:
            return self._language.name
        return None


class DiffAwareSyntaxHighlighter(SyntaxHighlighter):
    """
    Syntax highlighter that is aware of diff context.
    
    Adjusts highlighting based on line type (added, removed, unchanged).
    """
    
    def __init__(
        self,
        document: QTextDocument,
        language: Optional[str] = None,
        color_scheme: Optional[ColorScheme] = None
    ):
        super().__init__(document, language, color_scheme)
        
        self._line_types: Dict[int, str] = {}  # block number -> 'added', 'removed', 'unchanged'
        
        # Diff background colors
        self._added_bg = QColor(220, 255, 220, 100)
        self._removed_bg = QColor(255, 220, 220, 100)
        self._changed_bg = QColor(255, 255, 200, 100)
    
    def set_line_type(self, line: int, line_type: str) -> None:
        """Set the type of a line for diff-aware highlighting."""
        self._line_types[line] = line_type
    
    def set_line_types(self, types: Dict[int, str]) -> None:
        """Set types for multiple lines."""
        self._line_types = types
        self.rehighlight()
    
    def clear_line_types(self) -> None:
        """Clear all line type information."""
        self._line_types.clear()
        self.rehighlight()
    
    def highlightBlock(self, text: str) -> None:
        """Highlight with diff awareness."""
        block_num = self.currentBlock().blockNumber()
        line_type = self._line_types.get(block_num)
        
        # Apply diff background first
        if line_type == 'added':
            bg_format = QTextCharFormat()
            bg_format.setBackground(self._added_bg)
            self.setFormat(0, len(text), bg_format)
        elif line_type == 'removed':
            bg_format = QTextCharFormat()
            bg_format.setBackground(self._removed_bg)
            self.setFormat(0, len(text), bg_format)
        elif line_type == 'changed':
            bg_format = QTextCharFormat()
            bg_format.setBackground(self._changed_bg)
            self.setFormat(0, len(text), bg_format)
        
        # Apply syntax highlighting on top
        super().highlightBlock(text)


def create_highlighter_for_file(
    document: QTextDocument,
    filename: str,
    color_scheme: Optional[ColorScheme] = None
) -> SyntaxHighlighter:
    """
    Create a syntax highlighter for a file.
    
    Automatically detects language from filename.
    """
    highlighter = SyntaxHighlighter(document, color_scheme=color_scheme)
    highlighter.set_language_for_file(filename)
    return highlighter


def get_available_schemes() -> List[str]:
    """Get list of available color scheme names."""
    return ["Default Light", "Default Dark", "Monokai", "Solarized Light", "GitHub"]


def get_scheme_by_name(name: str) -> ColorScheme:
    """Get a color scheme by name."""
    schemes = {
        "Default Light": ColorSchemes.default_light,
        "Default Dark": ColorSchemes.default_dark,
        "Monokai": ColorSchemes.monokai,
        "Solarized Light": ColorSchemes.solarized_light,
        "GitHub": ColorSchemes.github,
    }
    
    factory = schemes.get(name, ColorSchemes.default_light)
    return factory()