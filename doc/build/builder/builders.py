from sphinx.application import TemplateBridge
from sphinx.builders.html import StandaloneHTMLBuilder
from sphinx.highlighting import PygmentsBridge
from sphinx.jinja2glue import BuiltinTemplateLoader
from pygments import highlight
from pygments.lexer import RegexLexer, bygroups, using
from pygments.token import *
from pygments.filter import Filter, apply_filters
from pygments.lexers import PythonLexer, PythonConsoleLexer
from pygments.formatters import HtmlFormatter, LatexFormatter
import re
from mako.lookup import TemplateLookup
from mako.template import Template
from mako import __version__

if __version__ < "0.4.1":
    raise Exception("Mako 0.4.1 or greater is required for "
                        "documentation build.")

class MakoBridge(TemplateBridge):
    def init(self, builder, *args, **kw):
        self.jinja2_fallback = BuiltinTemplateLoader()
        self.jinja2_fallback.init(builder, *args, **kw)

        self.layout = builder.config.html_context.get('mako_layout', 'html')
        builder.config.html_context['release_date'] = builder.config['release_date']
        builder.config.html_context['versions'] = builder.config['versions']

        self.lookup = TemplateLookup(directories=builder.config.templates_path,
            #format_exceptions=True, 
            imports=[
                "from builder import util"
            ]
        )

    def render(self, template, context):
        template = template.replace(".html", ".mako")
        context['prevtopic'] = context.pop('prev', None)
        context['nexttopic'] = context.pop('next', None)
        context['mako_layout'] = self.layout == 'html' and 'static_base.mako' or 'site_base.mako'
        # sphinx 1.0b2 doesn't seem to be providing _ for some reason...
        context.setdefault('_', lambda x:x)
        return self.lookup.get_template(template).render_unicode(**context)

    def render_string(self, template, context):
        # this is used for  .js, .css etc. and we don't have
        # local copies of that stuff here so use the jinja render.
        return self.jinja2_fallback.render_string(template, context)

class StripDocTestFilter(Filter):
    def filter(self, lexer, stream):
        for ttype, value in stream:
            if ttype is Token.Comment and re.match(r'#\s*doctest:', value):
                continue
            yield ttype, value

class PyConWithSQLLexer(RegexLexer):
    name = 'PyCon+SQL'
    aliases = ['pycon+sql']

    flags = re.IGNORECASE | re.DOTALL

    tokens = {
            'root': [
                (r'{sql}', Token.Sql.Link, 'sqlpopup'),
                (r'{opensql}', Token.Sql.Open, 'opensqlpopup'),
                (r'.*?\n', using(PythonConsoleLexer))
            ],
            'sqlpopup':[
                (
                    r'(.*?\n)((?:PRAGMA|BEGIN|SELECT|INSERT|DELETE|ROLLBACK|COMMIT|ALTER|UPDATE|CREATE|DROP|PRAGMA|DESCRIBE).*?(?:{stop}\n?|$))',
                    bygroups(using(PythonConsoleLexer), Token.Sql.Popup), 
                    "#pop"
                )
            ],
            'opensqlpopup':[
                (
                    r'.*?(?:{stop}\n*|$)',
                    Token.Sql, 
                    "#pop"
                )
            ]
        }


class PythonWithSQLLexer(RegexLexer):
    name = 'Python+SQL'
    aliases = ['pycon+sql']

    flags = re.IGNORECASE | re.DOTALL

    tokens = {
            'root': [
                (r'{sql}', Token.Sql.Link, 'sqlpopup'),
                (r'{opensql}', Token.Sql.Open, 'opensqlpopup'),
                (r'.*?\n', using(PythonLexer))
            ],
            'sqlpopup':[
                (
                    r'(.*?\n)((?:PRAGMA|BEGIN|SELECT|INSERT|DELETE|ROLLBACK|COMMIT|ALTER|UPDATE|CREATE|DROP|PRAGMA|DESCRIBE).*?(?:{stop}\n?|$))',
                    bygroups(using(PythonLexer), Token.Sql.Popup), 
                    "#pop"
                )
            ],
            'opensqlpopup':[
                (
                    r'.*?(?:{stop}\n*|$)',
                    Token.Sql, 
                    "#pop"
                )
            ]
        }


def _strip_trailing_whitespace(iter_):
    buf = list(iter_)
    if buf:
        buf[-1] = (buf[-1][0], buf[-1][1].rstrip())
    for t, v in buf:
        yield t, v

class PopupSQLFormatter(HtmlFormatter):
    def _format_lines(self, tokensource):
        buf = []
        for ttype, value in apply_filters(tokensource, [StripDocTestFilter()]):
            if ttype in Token.Sql:
                for t, v in HtmlFormatter._format_lines(self, iter(buf)):
                    yield t, v
                buf = []

                if ttype is Token.Sql:
                    yield 1, "<div class='show_sql'>%s</div>" % re.sub(r'(?:[{stop}|\n]*)$', '', value)
                elif ttype is Token.Sql.Link:
                    yield 1, "<a href='#' class='sql_link'>sql</a>"
                elif ttype is Token.Sql.Popup:
                    yield 1, "<div class='popup_sql'>%s</div>" % re.sub(r'(?:[{stop}|\n]*)$', '', value)
            else:
                buf.append((ttype, value))

        for t, v in _strip_trailing_whitespace(HtmlFormatter._format_lines(self, iter(buf))):
            yield t, v

class PopupLatexFormatter(LatexFormatter):
    def _filter_tokens(self, tokensource):
        for ttype, value in apply_filters(tokensource, [StripDocTestFilter()]):
            if ttype in Token.Sql:
                if ttype is not Token.Sql.Link and ttype is not Token.Sql.Open:
                    yield Token.Literal, re.sub(r'{stop}', '', value)
                else:
                    continue
            else:
                yield ttype, value

    def format(self, tokensource, outfile):
        LatexFormatter.format(self, self._filter_tokens(tokensource), outfile)

def autodoc_skip_member(app, what, name, obj, skip, options):
    if what == 'class' and skip and name in ('__init__', '__eq__', '__ne__', '__lt__', '__le__') and obj.__doc__:
        return False
    else:
        return skip

def setup(app):
    app.add_lexer('pycon+sql', PyConWithSQLLexer())
    app.add_lexer('python+sql', PythonWithSQLLexer())
    app.add_config_value('release_date', "", True)
    app.add_config_value('versions', "", True)
    app.connect('autodoc-skip-member', autodoc_skip_member)
    PygmentsBridge.html_formatter = PopupSQLFormatter
    PygmentsBridge.latex_formatter = PopupLatexFormatter

