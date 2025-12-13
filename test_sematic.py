import re
from dataclasses import dataclass
from typing import List, Optional
# for GUI display (if needed)
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
# ===========================================================

# ============================================================
# 1) Keywords & Categories
# ============================================================
categories = {
    # Program structure
    "SUMMON GAME": ("ProgramStructure", "Start"),
    "RECALL BASE": ("ProgramStructure", "End"),
    "USE": ("ProgramStructure", "Import"),

    # Variables / Types
    "BUILD": ("Variables", "Declaration"),
    "CHAMPION": ("Variables", "StringType"),
    "POWER": ("Variables", "IntType"),
    "MANA": ("Variables", "FloatType"),
    "BUFF": ("Variables", "BoolType"),

    # I/O
    "SAY": ("InputOutput", "Print"),
    "LISTEN TO": ("InputOutput", "Input"),

    # Functions
    "ULTIMATE": ("Functions", "Definition"),
    "CALL": ("Functions", "Call"),
    "BASE": ("Functions", "End"),

    # Control flow
    "CHECK": ("ControlFlow", "If"),
    "MISS": ("ControlFlow", "Else"),
    "FARM": ("ControlFlow", "Loop"),
    "FF15": ("ControlFlow", "Break"),
}

# ============================================================
# 2) Tokenization
# ============================================================
multi_keywords = sorted(categories.keys(), key=len, reverse=True)
keyword_variants = []
for k in multi_keywords:
    keyword_variants.append(re.escape(k))
    if " " in k:
        keyword_variants.append(re.escape(k.replace(" ", "_")))

# ensure keywords are matched only as whole words, not as prefixes of identifiers
keywords_pattern = r"\b(?:" + "|".join(keyword_variants) + r")\b"

token_specification = [
    ("COMMENT",   r"//.*"),
    ("WHITESPACE", r"\s+"),
    ("STRING",    r'"(?:[^"\\]|\\.)*"'),
    ("NUMBER",    r"\b\d+(?:\.\d+)?\b"),
    ("KEYWORD",   keywords_pattern),
    ("IDENTIFIER", r"\b[A-Za-z_]\w*\b"),
    ("OPERATOR",  r"(==|!=|<=|>=|\+\+|--|[+\-*/=<>])"),
    ("SYMBOL",    r"[{}\[\]\(\);,\.]"),
    ("MISMATCH",  r"."),  # fallback
]

master_pattern = re.compile("|".join(
    f"(?P<{name}>{pattern})" for name, pattern in token_specification
), flags=re.IGNORECASE)


@dataclass
class Token:
    type: str
    value: str
    category: Optional[tuple] = None
    line: int = 0
    column: int = 0

    def __repr__(self):
        if self.category:
            return f"{self.type:<10} {self.value:<20} (line {self.line}, col {self.column}) -> {self.category}"
        return f"{self.type:<10} {self.value:<20} (line {self.line}, col {self.column})"
    

def tokenize(code: str):
    line_num = 1
    line_start = 0
    for mo in master_pattern.finditer(code):
        kind = mo.lastgroup
        raw = mo.group()
        column = mo.start() - line_start + 1

        if kind in ("WHITESPACE", "COMMENT"):
            if "\n" in raw:
                line_num += raw.count("\n")
                line_start = mo.end()
            continue

        display_val = raw.replace("_", " ").upper()
        cat = None
        if kind == "KEYWORD":
            cat = categories.get(display_val)

        tok = Token(kind, display_val, cat, line_num, column)
        yield tok

        if "\n" in raw:
            line_num += raw.count("\n")
            line_start = mo.end()

    yield Token("EOF", "EOF", None, line_num, 1)


# ============================================================
# 3) AST Node
# ============================================================
class Node:
    def __init__(self, name: str, token: Optional[Token] = None):
        self.name = name
        self.token = token
        self.children: List['Node'] = []

    def add_child(self, child: Optional['Node']):
        if child is not None:
            self.children.append(child)

    def __repr__(self, level: int = 0) -> str:
        indent = "  " * level
        if self.token:
            return f"{indent}{self.name}: {self.token.value}"
        s = f"{indent}{self.name}"
        for c in self.children:
            s += "\n" + c.__repr__(level + 1)
        return s


# ============================================================
# 4) Parser
# ============================================================
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = list(tokens)
        self.pos = 0
        self.current_token: Optional[Token] = self.tokens[self.pos] if self.tokens else None
        self.errors: List[str] = []
        self.hard_error = False

    def advance(self):
        self.pos += 1
        self.current_token = self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def format_found(self):
        if not self.current_token:
            return "EOF"
        t = self.current_token
        return f"{t.type}('{t.value}')"

    
    def error(self, expected):
        # If we've already halted, don't append more errors
        if self.hard_error:
            return

        msg = f"{self.format_found()} expected {expected!r}"
        self.errors.append(msg)

        # Hard stop: prevent further parsing and errors
        self.hard_error = True
        # Force EOF token so loops exit cleanly
        self.current_token = Token("EOF", "EOF", None,
                                   self.current_token.line if self.current_token else 0,
                                   self.current_token.column if self.current_token else 0)

    def detect_keyword_typo(self):
        tok = self.current_token
        if not tok or tok.type != "IDENTIFIER":
            return False

        for kw in categories.keys():
            if tok.value.startswith(kw) and len(tok.value) > len(kw):
                # Create the single message user wants
                msg = f"found {tok.value} expected {kw} in line {tok.line}, col {tok.column}"
                # replace errors with only this message
                self.errors = [msg]

                # Hard stop now
                self.hard_error = True
                self.current_token = Token("EOF", "EOF", None, tok.line, tok.column)
                return True
        return False

    def match(self, expected_type, expected_value=None):
        if self.hard_error:
            return None

        if self.current_token and self.current_token.type == expected_type:
            if expected_value is None or self.current_token.value == expected_value:
                tok = self.current_token
                self.advance()
                return tok
        expected = expected_value if expected_value else expected_type
        self.error(expected)
        return None
    # Program
    def parse_program(self):
        root = Node("Program")

        while self.current_token and self.current_token.value == "USE":
            root.add_child(self.parse_import())

        if self.current_token and self.current_token.value == "SUMMON GAME":
            root.add_child(Node("ProgramStart", self.match("KEYWORD", "SUMMON GAME")))
        else:
            self.error("SUMMON GAME")

        root.add_child(self.parse_statement_list(stop_tokens=["RECALL BASE"]))

        if self.current_token and self.current_token.value == "RECALL BASE":
            root.add_child(Node("ProgramEnd", self.match("KEYWORD", "RECALL BASE")))
        else:
            self.error("RECALL BASE")

        # NOTE: no printing here — main will decide what to show
        return root

    # Statements
    def parse_statement_list(self, stop_tokens=None):
        if stop_tokens is None:
            stop_tokens = ["RECALL BASE", "BASE", "}"]
        node = Node("StatementList")
        while (self.current_token and self.current_token.value not in stop_tokens) and (not self.hard_error):
            stmt = self.parse_statement()
            if stmt:
                node.add_child(stmt)
            else:
                if self.current_token:
                    self.advance()
        return node

    def parse_statement(self):

                # Handle bare block { ... }
        if self.current_token and self.current_token.type == "SYMBOL" and self.current_token.value == "{":
            return self.parse_block()

       
        if self.hard_error:
            return None
         
        if not self.current_token:
            return None      
              
        # If the current token looks like a mistyped keyword (e.g. CHECKj), detect it first.
        if self.detect_keyword_typo():
            return None

        v = self.current_token.value
        mapping = {
            "USE": self.parse_import,
            "BUILD": self.parse_declaration,
            "SAY": self.parse_output,
            "LISTEN TO": self.parse_input,
            "ULTIMATE": self.parse_function,
            "CALL": self.parse_call,
            "CHECK": self.parse_if,
            "MISS": self.parse_else,
            "FARM": self.parse_loop,
            "FF15": self.parse_break,
            "RECALL BASE": self.parse_recall,
        }
        fn = mapping.get(v)
        if fn:
            return fn()
        # self.error(f"statement (one of {list(mapping.keys())})")
        if self.current_token and self.current_token.type == "IDENTIFIER":
            nxt_pos = self.pos + 1
            if nxt_pos < len(self.tokens):
                nxt = self.tokens[nxt_pos]
                if nxt.type == "OPERATOR" and nxt.value == "=":
                    return self.parse_assignment()
        return None
    # Specific statements
    def parse_import(self):
        n = Node("ImportStmt")
        n.add_child(Node("USE", self.match("KEYWORD", "USE")))
        n.add_child(Node("Identifier", self.match("IDENTIFIER")))
        return n

    def parse_summon(self):
        n = Node("ProgramStart")
        n.add_child(Node("SUMMON GAME", self.match("KEYWORD", "SUMMON GAME")))
        return n

    def parse_recall(self):
        n = Node("ProgramEnd")
        n.add_child(Node("RECALL BASE", self.match("KEYWORD", "RECALL BASE")))
        return n

    def parse_declaration(self):
        n = Node("Declaration")
        n.add_child(Node("BUILD", self.match("KEYWORD", "BUILD")))
        n.add_child(Node("Type", self.match("KEYWORD")))  # CHAMPION, POWER, ...
        n.add_child(Node("Identifier", self.match("IDENTIFIER")))
        n.add_child(Node("Operator", self.match("OPERATOR", "=")))
        n.add_child(self.parse_expr())
        return n

    def parse_assignment(self):
        """
        Parse: <IDENTIFIER> '=' <expr>
        Produces Node("Assignment") with children: Identifier, Operator('='), Expr
        """
        n = Node("Assignment")
        # Identifier (left-hand side)
        idtok = self.match("IDENTIFIER")
        n.add_child(Node("Identifier", idtok))
        # '=' operator
        n.add_child(Node("Operator", self.match("OPERATOR", "=")))
        # right-hand expression
        n.add_child(self.parse_expr())
        return n
    
    def parse_output(self):
        n = Node("OutputStmt")
        n.add_child(Node("SAY", self.match("KEYWORD", "SAY")))
        n.add_child(self.parse_expr())
        return n

    def parse_input(self):
        n = Node("InputStmt")
        n.add_child(Node("LISTEN TO", self.match("KEYWORD", "LISTEN TO")))
        n.add_child(Node("Identifier", self.match("IDENTIFIER")))
        return n

    def parse_function(self):
        n = Node("FunctionStmt")
        n.add_child(Node("ULTIMATE", self.match("KEYWORD", "ULTIMATE")))
        n.add_child(Node("Identifier", self.match("IDENTIFIER")))
        self.match("SYMBOL", "(")
        self.match("SYMBOL", ")")
        self.match("SYMBOL", "{")
        body = self.parse_statement_list(stop_tokens=["BASE", "}"])
        body_node = Node("Body")
        body_node.add_child(body)
        n.add_child(body_node)
        if self.current_token and self.current_token.value == "BASE":
            n.add_child(Node("BASE", self.match("KEYWORD", "BASE")))
        if self.current_token and self.current_token.value == "}":
            self.match("SYMBOL", "}")
        return n

    def parse_call(self):
        n = Node("CallStmt")
        n.add_child(Node("CALL", self.match("KEYWORD", "CALL")))
        n.add_child(Node("Identifier", self.match("IDENTIFIER")))
        return n

    def parse_if(self):
        n = Node("IfStmt")
        n.add_child(Node("CHECK", self.match("KEYWORD", "CHECK")))
        self.match("SYMBOL", "(")
        n.add_child(self.parse_expr())
        self.match("SYMBOL", ")")
        self.match("SYMBOL", "{")
        if_body = self.parse_statement_list(stop_tokens=["}"])
        if_body_node = Node("If_Body")
        if_body_node.add_child(if_body)
        n.add_child(if_body_node)
        self.match("SYMBOL", "}")
        if self.current_token and self.current_token.value == "MISS":
            n.add_child(self.parse_else())
        return n

    def parse_else(self):
        n = Node("ElseStmt")
        n.add_child(Node("MISS", self.match("KEYWORD", "MISS")))
        self.match("SYMBOL", "{")
        else_body = self.parse_statement_list(stop_tokens=["}"])
        else_body_node = Node("Else_Body")
        else_body_node.add_child(else_body)
        n.add_child(else_body_node)
        self.match("SYMBOL", "}")
        return n

    def parse_loop(self):
        n = Node("LoopStmt")
        n.add_child(Node("FARM", self.match("KEYWORD", "FARM")))
        self.match("SYMBOL", "(")
        n.add_child(self.parse_expr())
        self.match("SYMBOL", ")")
        self.match("SYMBOL", "{")
        loop_body = self.parse_statement_list(stop_tokens=["BASE", "}"])
        loop_body_node = Node("Body")
        loop_body_node.add_child(loop_body)
        n.add_child(loop_body_node)
        if self.current_token and self.current_token.value == "BASE":
            n.add_child(Node("BASE", self.match("KEYWORD", "BASE")))
        if self.current_token and self.current_token.value == "}":
            self.match("SYMBOL", "}")
        return n

    def parse_block(self):
        """
            Parse a bare block: { <statements> }
            Returns a Node("Block") whose child is a StatementList.
        """
        n = Node("Block")
        # match opening brace
        self.match("SYMBOL", "{")
        # parse until closing brace
        body = self.parse_statement_list(stop_tokens=["}"])
        body_node = Node("Body")
        body_node.add_child(body)
        n.add_child(body_node)
        # match closing brace
        if self.current_token and self.current_token.value == "}":
            self.match("SYMBOL", "}")
        return n
   
    


    def parse_break(self):
        n = Node("BreakStmt")
        n.add_child(Node("FF15", self.match("KEYWORD", "FF15")))
        return n

    # Expressions
  

    # --------------------------
    # Expression parsing (precedence climbing)
    # --------------------------
    # Precedence map: higher number = higher precedence
    PRECEDENCE = {
        "||": 1,
        "&&": 2,
        "==": 3, "!=": 3,
        "<": 4, ">": 4, "<=": 4, ">=": 4,
        "+": 5, "-": 5,
        "*": 6, "/": 6,
    }

    def parse_expr(self, min_prec: int = 0):
        """
        Precedence-climbing parser for binary operators.
        Starts by parsing a prefix (unary/factor), then consumes
        any binary operators with precedence >= min_prec.
        """
        left = self.parse_unary()

        # while there's an operator with precedence >= min_prec
        while (
            self.current_token
            and self.current_token.type == "OPERATOR"
            and self.current_token.value in self.PRECEDENCE
            and self.PRECEDENCE[self.current_token.value] >= min_prec
        ):
            op_tok = self.match("OPERATOR")  # consumes operator
            if not op_tok:
                break

            prec = self.PRECEDENCE[op_tok.value]

            # For left-associative ops we use next_min = prec + 1
            # (If you need right-associative ops like "^", set next_min = prec)
            next_min = prec + 1

            # parse right-hand side with higher min precedence
            right = self.parse_expr(next_min)

            # build a binary node: (left op right)
            new_node = Node("Expr")
            new_node.add_child(left)
            new_node.add_child(Node("Operator", op_tok))
            new_node.add_child(right)
            left = new_node

        return left

    def parse_unary(self):
        """
        Handle unary operators like '-' and '!' before a factor.
        If there's no unary operator, delegate to parse_factor().
        """
        if self.current_token and self.current_token.type == "OPERATOR" and self.current_token.value in ("+", "-", "!"):
            op_tok = self.match("OPERATOR")
            operand = self.parse_unary()  # allow chained unary operators
            node = Node("UnaryExpr")
            node.add_child(Node("Operator", op_tok))
            node.add_child(operand)
            return node
        return self.parse_factor()

    def parse_factor(self):
        """
        Parse the basic units: NUMBER, STRING, IDENTIFIER, parenthesized expr,
        and simple function-style calls like ident(...) (zero or more comma-separated args).
        """
        t = self.current_token
        if not t:
            self.error("Unexpected end of input in expression")
            return None

        # Number
        if t.type == "NUMBER":
            return Node("Number", self.match("NUMBER"))

        # String
        if t.type == "STRING":
            return Node("String", self.match("STRING"))

        # Parenthesized expression
        if t.type == "SYMBOL" and t.value == "(":
            self.match("SYMBOL", "(")
            node = self.parse_expr()
            self.match("SYMBOL", ")")
            return node

        # Identifier (variable or function-call)
        if t.type == "IDENTIFIER":
            ident_tok = self.match("IDENTIFIER")
            # function-style call: IDENTIFIER ( arg1, arg2 )
            if self.current_token and self.current_token.type == "SYMBOL" and self.current_token.value == "(":
                call_node = Node("CallExpr")
                call_node.add_child(Node("Identifier", ident_tok))
                self.match("SYMBOL", "(")
                # parse zero or more arguments separated by commas
                args_node = Node("Args")
                if self.current_token and self.current_token.value != ")":
                    while True:
                        arg = self.parse_expr()
                        args_node.add_child(arg)
                        if self.current_token and self.current_token.type == "SYMBOL" and self.current_token.value == ",":
                            self.match("SYMBOL", ",")
                            continue
                        break
                call_node.add_child(args_node)
                self.match("SYMBOL", ")")
                return call_node
            # otherwise plain identifier
            return Node("Identifier", ident_tok)

        # Unknown token in factor
        self.error(f"Unexpected token '{t.value}' in expression")
        # advance already called by error(); try to return None to let caller handle it
        return None


    def parse_term(self):
        node = self.parse_factor()
        while self.current_token and self.current_token.value in ["*", "/"]:
            op = Node("Operator", self.match("OPERATOR"))
            new_node = Node("Term")
            new_node.add_child(node)
            new_node.add_child(op)
            new_node.add_child(self.parse_factor())
            node = new_node
        return node


# ============================================================
# 5) Semantic: simple symbol table + analyzer
# ============================================================
from dataclasses import dataclass

# basic types used by the semantic checker
DATA_TYPE_STRING = "DATA_TYPE_STRING"
DATA_TYPE_INT    = "DATA_TYPE_INT"
DATA_TYPE_FLOAT = "DATA_TYPE_FLOAT"
DATA_TYPE_BOOL   = "DATA_TYPE_BOOL"
DATA_TYPE_UNKNOWN= "DATA_TYPE_UNKNOWN"

# map your keyword types to semantic data types
KEYWORD_TO_DTYPE = {
    "CHAMPION": DATA_TYPE_STRING,
    "POWER":    DATA_TYPE_INT,
    "MANA":     DATA_TYPE_FLOAT,
    "BUFF":     DATA_TYPE_BOOL,
}

@dataclass
class IdentifierInfo:
    name: str
    dtype: str
    line: int

class SymbolTable:
    def __init__(self):
        # list of dicts representing nested scopes; index -1 is current scope
        self.scopes: List[dict] = [{}]  # start with global scope

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()
        else:
            # ignore popping global scope
            pass

    def declare(self, name: str, dtype: str, line: int) -> Optional[IdentifierInfo]:
        current = self.scopes[-1]
        if name in current:
            return None  # redeclaration
        info = IdentifierInfo(name, dtype, line)
        current[name] = info
        return info

    def lookup(self, name: str) -> Optional[IdentifierInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def entries(self):
        # returns a flattened view (for printing)
        flat = {}
        for i, s in enumerate(self.scopes):
            for k, v in s.items():
                flat[k] = v
        return flat

    def __repr__(self):
        lines = []
        for i, s in enumerate(self.scopes):
            lines.append(f"Scope {i}:")
            for k, v in s.items():
                lines.append(f"  {k}: {v.dtype} (declared line {v.line})")
        return "\n".join(lines)


def data_type_check(t1: str, t2: str, operator: str) -> Optional[str]:
    # assignment
    if operator == "=":
        # allow int/Float compatibility (int <-> Float)
        if t1 == t2:
            return t1
        if (t1 == DATA_TYPE_FLOAT and t2 == DATA_TYPE_INT) or (t1 == DATA_TYPE_INT and t2 == DATA_TYPE_FLOAT):
            return DATA_TYPE_FLOAT
        return None

    # arithmetic
    if operator in {"+", "-", "*", "/"}:
        if t1 == DATA_TYPE_STRING or t2 == DATA_TYPE_STRING:
             #   here we allow concatenation between string and int # only allow + between strings (concatenation)
            if operator == "+" : # and t1 == DATA_TYPE_STRING and t2 == DATA_TYPE_STRING
                return DATA_TYPE_STRING
            return None
        if t1 == DATA_TYPE_FLOAT or t2 == DATA_TYPE_FLOAT:
            return DATA_TYPE_FLOAT
        if t1 == DATA_TYPE_INT and t2 == DATA_TYPE_INT:
            return DATA_TYPE_INT
        return None

    # comparison -> bool (==, !=, <, >, <=, >=)
    if operator in {"==", "!=", "<", ">", "<=", ">="}:
        if t1 == t2:
            return DATA_TYPE_BOOL
        if {t1, t2} <= {DATA_TYPE_INT, DATA_TYPE_FLOAT}:
            return DATA_TYPE_BOOL
        return None

    return None


# Semantic analyzer: simple AST walker for your Node shape
class SemanticAnalyzer:
    def __init__(self, root: Node):
        self.root = root
        self.symtab = SymbolTable()
        self.errors: List[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def analyze(self):
        # Program root expected
        self.visit(self.root)
        return self.errors

    def visit(self, node: Optional[Node]):
        if node is None:
            return None

        handler_name = f"visit_{node.name}"
        if hasattr(self, handler_name):
            return getattr(self, handler_name)(node)
        # generic traversal
        for c in node.children:
            self.visit(c)
    

    def visit_Block(self, node: Node):
        # Block creates a new local scope
        self.symtab.push_scope()
        # Body node is a child containing the StatementList
        body = next((c for c in node.children if c.name == "Body"), None)
        if body:
            self.visit(body)
        self.symtab.pop_scope()

    # Handlers for nodes produced by your parser
    def visit_Program(self, node: Node):
        # global scope already present
        for c in node.children:
            self.visit(c)


    def visit_Declaration(self, node: Node):
        # children: BUILD, Type, Identifier, Operator('='), Expr
        tnode = next((c for c in node.children if c.name == "Type"), None)
        idnode = next((c for c in node.children if c.name == "Identifier"), None)
        exprnode = next((c for c in node.children if c.name not in ("BUILD", "Type", "Identifier", "Operator")), None)

        if not tnode or not idnode:
            return

        kw_type = tnode.token.value  # e.g. "CHAMPION" etc.
        dtype = KEYWORD_TO_DTYPE.get(kw_type, DATA_TYPE_UNKNOWN)
        name = idnode.token.value

        # declare
        declared = self.symtab.declare(name, dtype, idnode.token.line)
        if declared is None:
            self.error(f"Semantic Error: Redeclaration of '{name}' at line {idnode.token.line}")
            return

        # check initializer if present
        if exprnode:
            expr_type = self.eval_expr_type(exprnode)
            if expr_type is None:
                self.error(f"Semantic Error: cannot infer type of initializer for '{name}' at line {idnode.token.line}")
                return
            # check assignment compatibility
            if data_type_check(dtype, expr_type, "=") is None:
                self.error(f"Semantic Error: cannot assign {expr_type} to {dtype} for '{name}' at line {idnode.token.line}")

    def visit_Assignment(self, node: Node):
        # children: Identifier, Operator('='), Expr
        idnode = next((c for c in node.children if c.name == "Identifier"), None)
        exprnode = next((c for c in node.children if c.name not in ("Identifier", "Operator")), None)
        if not idnode or not exprnode:
            return
        name = idnode.token.value
        info = self.symtab.lookup(name)
        if info is None:
            self.error(f"Semantic Error: Undeclared identifier '{name}' at line {idnode.token.line}")
            return
        expr_type = self.eval_expr_type(exprnode)
        if expr_type is None:
            self.error(f"Semantic Error: cannot infer type of assignment to '{name}' at line {idnode.token.line}")
            return
        if data_type_check(info.dtype, expr_type, "=") is None:
            self.error(f"Semantic Error: cannot assign {expr_type} to {info.dtype} for '{name}' at line {idnode.token.line}")

    def visit_OutputStmt(self, node: Node):
        # SAY expr
        exprnode = next((c for c in node.children if c.name != "SAY"), None)
        if not exprnode:
            return
        t = self.eval_expr_type(exprnode)
        if t is None:
            self.error(f"Semantic Error: invalid expression in SAY at line {node.token.line if node.token else '?'}")

    def visit_IfStmt(self, node: Node):
        # CHECK <expr> { body }
        cond = None
        for c in node.children:
            if c.name != "CHECK" and c.name != "If_Body":
                cond = c
                break
        if cond:
            t = self.eval_expr_type(cond)
            if t != DATA_TYPE_BOOL:
                self.error(f"Semantic Error: condition in CHECK must be boolean at line {cond.token.line if cond.token else '?'}")
        # enter a new scope for the if body
        self.symtab.push_scope()
        body = next((c for c in node.children if c.name == "If_Body"), None)
        if body:
            self.visit(body)
        self.symtab.pop_scope()

    def visit_ElseStmt(self, node: Node):
        self.symtab.push_scope()
        body = next((c for c in node.children if c.name == "Else_Body"), None)
        if body:
            self.visit(body)
        self.symtab.pop_scope()

    def visit_FunctionStmt(self, node: Node):
        self.symtab.push_scope()
        body = next((c for c in node.children if c.name == "Body"), None)
        if body:
            self.visit(body)
        self.symtab.pop_scope()

    def visit_StatementList(self, node: Node):
        for c in node.children:
            self.visit(c)

    # evaluate expression node types (returns one of DATA_TYPE_*, or None)
    def eval_expr_type(self, node: Node) -> Optional[str]:
        if node is None:
            return None
        # Node types created by parser: Number, String, Identifier, Expr, UnaryExpr, CallExpr, Term, etc.
        if node.name == "Number":
            tok = node.token
            if "." in tok.value:
                return DATA_TYPE_FLOAT
            return DATA_TYPE_INT
        if node.name == "String":
            return DATA_TYPE_STRING
        if node.name == "Identifier":
            info = self.symtab.lookup(node.token.value)
            if info:
                return info.dtype
            else:
                self.error(f"Semantic Error: Undeclared identifier '{node.token.value}' at line {node.token.line}")
                return None
        
        if node.name == "CallExpr":
            # no functions defined; return None (unknown)
            return None

        if node.name in ("Expr", "Term"):
            left = node.children[0]
            opnode = node.children[1]
            right = node.children[2]
            left_t = self.eval_expr_type(left)
            right_t = self.eval_expr_type(right)
            if left_t is None or right_t is None:
                return None
            op = opnode.token.value if opnode.token else None
            return data_type_check(left_t, right_t, op)

        # If node is a wrapper (Body, If_Body, Args, etc.) try descending
        for c in node.children:
            t = self.eval_expr_type(c)
            if t is not None:
                return t
        return None


# ============================================================
# 6) Example / main behavior: print only errors if any and run semantics

#  <= >= == !=    = > < + - 
# ============================================================
# if __name__ == "__main__":
#     code = '''
#     SUMMON GAME

#     BUILD CHAMPION name = "Garen"
#     BUILD POWER gold = "jghedhg"
#     BUILD MANA gold2 = 1.1
#     SAY "Welcome, " + name + "!"

#     name = name + 1


#     CHECK (gold >= 1000 ) {
#         BUILD BUFF isRich = true
#         SAY "You're rich!"
#     }
    
#     MISS {
#         SAY "Keep FARMING!"
#     }


#     RECALL BASE
    
#     '''

#     tokens = list(tokenize(code))
#     parser = Parser(tokens)
#     tree = parser.parse_program()

#     # show parse errors if present; otherwise show the parse tree
#     if parser.errors:
#         print("\n❌ Parsing completed with errors:")
#         for e in parser.errors:
#             print(e)
#     else:
#         print("\n--- PARSE TREE ---")
#         print(tree)

#         # run semantic analysis
#         analyzer = SemanticAnalyzer(tree)
#         sem_errors = analyzer.analyze()
#         if sem_errors:
#             print("\n❌ Semantic errors:")
#             for e in sem_errors:
#                 print(e)
#         else:
#             print("\n✔️ Semantic OK — symbol table:")
#             print(analyzer.symtab)



# ============================================================
def run_compiler():
    code = code_editor.get("1.0", tk.END)

    output_box.config(state="normal")
    output_box.delete("1.0", tk.END)

    try:
        tokens = list(tokenize(code))
        parser = Parser(tokens)
        tree = parser.parse_program()

        # Parsing errors
        if parser.errors:
            output_box.insert(tk.END, "❌ Parsing Errors:\n")
            for e in parser.errors:
                output_box.insert(tk.END, e + "\n")
        else:
            output_box.insert(tk.END, "✔ Parsing Successful\n\n")
            output_box.insert(tk.END, "--- PARSE TREE ---\n")
            output_box.insert(tk.END, str(tree) + "\n\n")

            analyzer = SemanticAnalyzer(tree)
            sem_errors = analyzer.analyze()

            if sem_errors:
                output_box.insert(tk.END, "❌ Semantic Errors:\n")
                for e in sem_errors:
                    output_box.insert(tk.END, e + "\n")
            else:
                output_box.insert(tk.END, "✔ Semantic OK\n\n")
                output_box.insert(tk.END, "--- SYMBOL TABLE ---\n")
                output_box.insert(tk.END, str(analyzer.symtab))

    except Exception as ex:
        output_box.insert(tk.END, f"Runtime Error: {ex}")

    output_box.config(state="disabled")
# ================= GUI =================

root = tk.Tk()
root.title("LeagueLang Compiler")
root.geometry("1000x600")

# Main layout
main_frame = ttk.Frame(root)
main_frame.pack(fill="both", expand=True)

main_frame.columnconfigure(0, weight=1)
main_frame.columnconfigure(1, weight=1)
main_frame.rowconfigure(1, weight=1)

# Top bar
run_button = ttk.Button(main_frame, text="Run ▶", command=run_compiler)
run_button.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)

# Code editor (left)
code_editor = ScrolledText(main_frame, wrap="word")
code_editor.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

# Output area (right)
output_box = ScrolledText(main_frame, wrap="word", state="disabled")
output_box.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

# Sample code
code_editor.insert(tk.END, """SUMMON GAME

BUILD CHAMPION name = "Garen"
BUILD POWER gold = 1000

SAY "Welcome " + name

RECALL BASE
""")

root.mainloop()