# mypy: disable-error-code="override, assignment"
"""
Enhanced DOCX Jinja2 validation with intelligent filter handling.
"""
from typing import Callable, Optional, Set, List
from jinja2 import DebugUndefined
from jinja2.utils import missing
from docxtpl import DocxTemplate
from jinja2 import Environment, BaseLoader
from jinja2.ext import Extension
from jinja2.lexer import Token
import traceback
import jinja2.exceptions
import re

__all__ = ["CallAndDebugUndefined", "get_jinja_errors", "Environment", "BaseLoader"]


class DAIndexError(IndexError):
    pass


class DAAttributeError(AttributeError):
    pass


nameerror_match = re.compile(
    r"\'(.*)\' (is not defined|referenced before assignment|is undefined)"
)


def extract_missing_name(the_error):
    m = nameerror_match.search(str(the_error))
    if m:
        return m.group(1)
    raise the_error


class DAEnvironment(Environment):
    def from_string(self, source, **kwargs):  # pylint: disable=arguments-differ
        source = re.sub(r"({[\%\{].*?[\%\}]})", fix_quotes, source)
        return super().from_string(source, **kwargs)

    def getitem(self, obj, argument):
        try:
            return obj[argument]
        except (DAAttributeError, DAIndexError) as err:
            varname = extract_missing_name(err)
            return self.undefined(obj=missing, name=varname)
        except (AttributeError, TypeError, LookupError):
            return self.undefined(obj=obj, name=argument, accesstype="item")

    def getattr(self, obj, attribute):
        try:
            return getattr(obj, attribute)
        except DAAttributeError as err:
            varname = extract_missing_name(err)
            return self.undefined(obj=missing, name=varname)
        except:
            return self.undefined(obj=obj, name=attribute, accesstype="attribute")


def fix_quotes(match):
    instring = match.group(1)
    n = len(instring)
    output = ""
    i = 0
    while i < n:
        if instring[i] == "\u201c" or instring[i] == "\u201d":
            output += '"'
        elif instring[i] == "\u2018" or instring[i] == "\u2019":
            output += "'"
        elif instring[i] == "&" and i + 4 < n and instring[i : i + 5] == "&amp;":
            output += "&"
            i += 4
        else:
            output += instring[i]
        i += 1
    return output


class CallAndDebugUndefined(DebugUndefined):
    """Handles Jinja2 undefined errors by printing the name of the undefined variable.
    Extended to handle callable methods.
    """

    def __call__(self, *pargs, **kwargs):
        return self

    def __getattr__(self, _: str) -> "CallAndDebugUndefined":
        return self

    ## Define `<` and `>` ops, since we compare dates in docxs sometimes
    def __lt__(self, _):
        return True

    def __gt__(self, _):
        return False

    def __add__(self, _):
        return self

    def __sub__(self, _):
        return self

    def __format__(self, *y, **kwargs):
        return str(self)

    ## Things that handle `other_parties`
    def number(self):
        return 0

    def as_noun(self, *y):
        return str(self)

    # A specific handle for `name.full`
    def full(self):
        return str(self)

    __getitem__ = __getattr__  # type: ignore


null_func: Callable = lambda *args, **kwargs: args[0]

# Jinja filters that docassemble doesn't override, but
# we don't want to run (we're just checking that they exist)
builtin_jinja_filters = {
    "round": null_func,
    "Decimal": null_func
}

# From parse.py, get_builtin_jinja_filters()
builtin_docassemble_jinja_filters = {
    "ampersand_filter": null_func,
    "markdown": null_func,
    "add_separators": null_func,
    "inline_markdown": null_func,
    "paragraphs": null_func,
    "manual_line_breaks": null_func,
    "RichText": null_func,
    "groupby": null_func,
    "max": null_func,
    "min": null_func,
    "sum": null_func,
    "unique": null_func,
    "join": null_func,
    "attr": null_func,
    "selectattr": null_func,
    "rejectattr": null_func,
    "sort": null_func,
    "dictsort": null_func,
    "nice_number": null_func,
    "ordinal": null_func,
    "ordinal_number": null_func,
    "currency": null_func,
    "comma_list": null_func,
    "comma_and_list": null_func,
    "capitalize": null_func,
    "salutation": null_func,
    "alpha": null_func,
    "roman": null_func,
    "word": null_func,
    "bold": null_func,
    "italic": null_func,
    "title_case": null_func,
    "single_paragraph": null_func,
    "phone_number_formatted": null_func,
    "phone_number_in_e164": null_func,
    "country_name": null_func,
    "fix_punctuation": null_func,
    "redact": null_func,
    "verbatim": null_func,
    "map": null_func,
    "chain": null_func,
    "catchall_options": null_func,
    "catchall_label": null_func,
    "catchall_datatype": null_func,
    "catchall_question": null_func,
    "catchall_subquestion": null_func,
    "if_final": null_func,
    "any": any,
    "all": all,
}


class DAExtension(Extension):
    def parse(self, parser):
        raise NotImplementedError()

    def filter_stream(self, stream):
        # in_var = False
        met_pipe = False
        for token in stream:
            if token.type == "variable_begin":
                # in_var = True
                met_pipe = False
            if token.type == "variable_end":
                # in_var = False
                if not met_pipe:
                    yield Token(token.lineno, "pipe", None)
                    yield Token(token.lineno, "name", "ampersand_filter")
            # if in_var and token.type == 'pipe':
            #     met_pipe = True
            yield token


class ValidationResult:
    """Result of DOCX validation with separate error and warning tracking."""
    
    def __init__(self):
        self.syntax_errors: List[str] = []
        self.unknown_filters: Set[str] = set()
        self.warnings: List[str] = []
    
    @property
    def has_errors(self) -> bool:
        """True if there are syntax errors that should fail validation."""
        return bool(self.syntax_errors)
    
    @property
    def has_warnings(self) -> bool:
        """True if there are warnings (like unknown filters)."""
        return bool(self.warnings) or bool(self.unknown_filters)
    
    def add_syntax_error(self, error: str):
        """Add a syntax error that should cause validation to fail."""
        self.syntax_errors.append(error)
    
    def add_unknown_filter(self, filter_name: str):
        """Add an unknown filter name."""
        self.unknown_filters.add(filter_name)
    
    def add_warning(self, warning: str):
        """Add a general warning."""
        self.warnings.append(warning)
    
    def get_error_message(self) -> Optional[str]:
        """Get combined error message, or None if no errors."""
        if not self.has_errors:
            return None
        return "\n\n".join(self.syntax_errors)
    
    def get_warnings_message(self) -> Optional[str]:
        """Get combined warnings message, or None if no warnings."""
        if not self.has_warnings:
            return None
        
        parts = []
        
        # Add unknown filters
        if self.unknown_filters:
            filter_list = ", ".join(sorted(self.unknown_filters))
            parts.append(f"Unknown filters detected: {filter_list}")
        
        # Add other warnings
        if self.warnings:
            parts.extend(self.warnings)
        
        return "\n\n".join(parts)


def get_known_filters() -> Set[str]:
    """Return set of all known/expected filters that should not generate warnings."""
    return {
        # Built-in Jinja2 filters
        "abs", "attr", "batch", "capitalize", "center", "default", "dictsort",
        "escape", "filesizeformat", "first", "float", "forceescape", "format",
        "groupby", "indent", "int", "join", "last", "length", "list", "lower",
        "map", "max", "min", "pprint", "random", "reject", "rejectattr", "replace",
        "reverse", "round", "safe", "select", "selectattr", "slice", "sort",
        "string", "striptags", "sum", "title", "tojson", "trim", "truncate",
        "unique", "upper", "urlencode", "urlize", "wordcount", "wordwrap", "xmlattr",
        
        # Python built-ins commonly used as filters
        "any", "all", "enumerate", "sorted", "len",
        
        # Common Docassemble filters
        "ampersand_filter", "markdown", "add_separators", "inline_markdown",
        "paragraphs", "manual_line_breaks", "RichText", "nice_number", "ordinal",
        "ordinal_number", "currency", "comma_list", "comma_and_list", "salutation",
        "alpha", "roman", "word", "bold", "italic", "title_case", "single_paragraph",
        "phone_number_formatted", "phone_number_in_e164", "country_name",
        "fix_punctuation", "redact", "verbatim", "chain", "if_final",
        
        # Additional common Docassemble filters
        "catchall_options", "catchall_label", "catchall_datatype", 
        "catchall_question", "catchall_subquestion", "showifdef",
        "currency_symbol", "indefinite_article", "possessify",
        "verb_past", "verb_present", "noun_plural", "noun_singular",
        "some", "indefinite", "a_preposition_b", "preposition_b",
        "capitalize_function", "section_links", "url_action",
        "interview_url", "interview_email", "static_image",
        "qr_code", "overlay_pdf", "pdf_concatenate",
        
        # Date/time filters
        "strftime", "strptime", "today", "as_datetime", "format_date",
        "format_time", "current_datetime",
        
        # File/document filters  
        "file_size", "mime_type", "extension", "filename",
        
        # Math/calculation filters
        "float_to_currency", "percentage", "thousands",
    }


def validate_with_stubbed_filters(docx_path: str, filter_names: Set[str]) -> ValidationResult:
    """Validate DOCX with all specified filters stubbed out as no-ops."""
    result = ValidationResult()
    
    try:
        # Create environment with stubbed filters
        env = DAEnvironment(undefined=CallAndDebugUndefined, extensions=[DAExtension])
        
        # Import and add the existing builtin filters
        env.filters.update(builtin_jinja_filters)
        env.filters.update(builtin_docassemble_jinja_filters)
        
        # Add stub functions for the unknown filters
        null_func = lambda *args, **kwargs: args[0] if args else ""
        for filter_name in filter_names:
            env.filters[filter_name] = null_func
        
        # Try to render the template
        doc = DocxTemplate(docx_path)
        doc.render({}, jinja_env=env)
        
        # If we get here, validation succeeded
        return result
        
    except jinja2.exceptions.TemplateSyntaxError as e:
        # Still a real syntax error
        error_msg = str(e)
        extra_context = getattr(e, 'docx_context', [])
        if extra_context:
            error_msg += "\n\nContext:\n" + "\n".join(
                map(lambda x: "  " + x, extra_context)
            )
        result.add_syntax_error(error_msg)
        return result
        
    except Exception as e:
        result.add_syntax_error(f"Validation with stubbed filters failed: {traceback.format_exc()}")
        return result


def extract_filters_from_docx(docx_path: str) -> set:
    """Extract filter names from DOCX content using regex, regardless of syntax validity."""
    try:
        doc = DocxTemplate(docx_path)
        # Get the raw XML content
        xml_content = ""
        for element in doc.docx.element.body.iter():
            if element.text:
                xml_content += element.text + " "
        
        # Find all Jinja expressions with filters
        filter_pattern = r'\{\{[^}]*\|\s*([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(filter_pattern, xml_content)
        return set(matches)
    except Exception:
        return set()


def get_jinja_errors_with_warnings(the_file: str) -> ValidationResult:
    """
    Validate DOCX file for Jinja2 errors and warnings.
    Iteratively finds all unknown filters and treats them as warnings.
    """
    result = ValidationResult()
    
    # First, try to extract filters from the raw document content
    raw_filters = extract_filters_from_docx(the_file)
    
    # Keep track of all unknown filters we've found
    all_unknown_filters: Set[str] = set()
    all_syntax_errors = set()  # Track syntax errors to avoid duplicates
    max_iterations = 10  # Prevent infinite loops
    
    for iteration in range(max_iterations):
        # Try validation with current set of stubbed filters
        validation_result = validate_with_stubbed_filters(the_file, all_unknown_filters)
        
        if not validation_result.has_errors:
            # No more errors! We're done
            break
        
        # Check if any errors are about missing filters
        filter_errors = []
        other_errors = []
        
        for error in validation_result.syntax_errors:
            if "No filter named" in error:
                filter_errors.append(error)
            else:
                other_errors.append(error)
        
        # Add non-filter errors to our result (but avoid duplicates)
        for error in other_errors:
            if error not in all_syntax_errors:
                all_syntax_errors.add(error)
                result.syntax_errors.append(error)
        
        if not filter_errors:
            # No more filter errors found in validation, but check raw filters
            break
        
        # Extract filter names from the filter errors
        found_new_filter = False
        for error in filter_errors:
            filter_match = re.search(r"No filter named '([^']+)'", error)
            if filter_match:
                filter_name = filter_match.group(1)
                if filter_name not in all_unknown_filters:
                    all_unknown_filters.add(filter_name)
                    found_new_filter = True
        
        if not found_new_filter:
            # We didn't find any new filters, so we're stuck
            # Add remaining filter errors as syntax errors
            for error in filter_errors:
                if error not in all_syntax_errors:
                    all_syntax_errors.add(error)
                    result.syntax_errors.append(error)
            break
    
    # Add any filters we found in raw content that weren't caught by validation
    all_unknown_filters.update(raw_filters)
    
    # Only add truly unknown filters as warnings (exclude known filters)
    known_filters = get_known_filters()
    for filter_name in all_unknown_filters:
        if filter_name not in known_filters:
            result.add_unknown_filter(filter_name)
    
    return result


def get_jinja_errors(the_file: str) -> Optional[str]:
    """
    Legacy function for backward compatibility.
    Returns error message only, ignoring warnings.
    """
    result = get_jinja_errors_with_warnings(the_file)
    return result.get_error_message()
