import re
import xml.etree.ElementTree as ET
from selectolax.parser import HTMLParser
from IPython.display import Markdown, display


def convert_persian_digits(s: str) -> str:
    persian = '۰۱۲۳۴۵۶۷۸۹'
    arabic  = '٠١٢٣٤٥٦٧٨٩'
    ascii_  = '0123456789'
    return s.translate(str.maketrans(persian + arabic, ascii_ * 2))

def get_tag(elem):
    return elem.tag.split('}')[-1]

op_map = {
    'plus': '+', 'minus': '-', 'times': r'\times', 'divide': r'\div',
    'power': '^', 'root': 'sqrt', 'eq': '=', 'neq': r'\neq',
    'gt': '>', 'lt': '<', 'geq': r'\ge', 'leq': r'\le'
}

mo_map = {
    '+': '+', '-': '-', '*': r'\cdot', '/': '/', '^': '^', '_': '_',
    '(': '(', ')': ')', '[': '[', ']': ']', '{': '', '}': '',
    '×': r'\times', '÷': r'\div', '≠': r'\neq', '≤': r'\le',
    '≥': r'\ge', '±': r'\pm', '·': r'\cdot', '∞': r'\infty',
    '∑': r'\sum', '∏': r'\prod', '−': '-',
    '~': r'\sim', 'ˆ': r'\hat'
}

def mathml_to_latex_element(elem: ET.Element) -> str:
    tag = get_tag(elem)
    children = [mathml_to_latex_element(c) for c in elem]
    text = convert_persian_digits((elem.text or '').strip())
    if not text and not children:
        return ''
    if tag in ('math', 'mstyle'):
        return ''.join(children)

    if tag == 'mrow':
        if len(elem) >= 3:
            first_child_tag = get_tag(elem[0])
            last_child_tag = get_tag(elem[-1])
            first_child_text = (elem[0].text or '').strip()
            last_child_text = (elem[-1].text or '').strip()

            if (first_child_tag == 'mo' and first_child_text == '{') \
                and (last_child_tag == 'mo' and last_child_text == '}'):
                inner = ''.join(children[1:-1])
                return rf"\left\{{{inner}\right\}}"
        # Typical pattern: <mo>|</mo> <mtable/> <mtable/> <mtable/> <mo>|</mo>
        if len(elem) >= 4 and \
            get_tag(elem[0]) == 'mo' and (elem[0].text or '').strip() == '|' and \
            get_tag(elem[-1]) == 'mo' and (elem[-1].text or '').strip() == '|' and \
            all(get_tag(e) == 'mtable' for e in elem[1:-1]):
            # Compose columns from multiple mtable
            mtables = elem[1:-1]
            num_rows = max(len(mt.find('mtr') or mt.findall('mtr')) for mt in mtables)
            # Collect per-column lists
            cols = []
            for mt in mtables:
                mtrs = mt.findall('mtr')
                col = []
                for row in mtrs:
                    # Each mtr has a mrow or maybe just a single cell
                    mrow = row.find('mrow')
                    col.append(mathml_to_latex_element(mrow if mrow is not None else row))
                cols.append(col)
            # Now recompose: each row is ith cell from each col
            matrix = ''
            for i in range(len(cols[0])):   # assume all columns same length!
                matrix += ' & '.join(col[i] for col in cols) + r' \\'
            # Remove trailing '\\'
            matrix = matrix.rstrip(r'\\')
            return r"\left|\begin{matrix}" + matrix + r"\end{matrix}\right|"

        # ----- fallback to default mrow ------
        if len(children) == 1:
            return children[0]
        if len(children) == 2 and children[0] == '-':
            return f"-{children[1]}"
        if len(children) >= 3:
            result = ''
            i = 0
            while i < len(children):
                if i + 2 < len(children) and children[i + 1] == '^':
                    result += f"{children[i]}^{{{children[i + 2]}}}"
                    i += 3
                else:
                    result += children[i]
                    i += 1
            return result
        return ''.join(children)

    # --- Identifiers ---

    if tag == 'mi':
        # برای تشابه
        if text == '~':
            return r'\sim'
        if text.lower() in {'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'ln'}:
            return rf"\{text.lower()}"

        return rf"\mathrm{{{text}}}" if len(text) > 1 else text
    if tag == 'mn':
        return text
    if tag == 'mo':
        op = mo_map.get(text, text)
        # if it's a LaTeX command (begins with backslash), terminate it so
        # it doesn't eat the next letter:
        if op.startswith('\\'):
            return op + '{}'
        else:
            return op

    # --- Scripts ---
    if tag == 'msup':
        return f"{children[0]}^{{{children[1]}}}"
    if tag == 'msub':
        return f"{children[0]}_{{{children[1]}}}"
    if tag == 'msubsup':
        return f"{children[0]}_{{{children[1]}}}^{{{children[2]}}}"
    if tag == 'mmultiscripts':
        base = children[0]
        sub = f"_{{{children[1]}}}" if len(children) > 1 else ''
        sup = f"^{{{children[2]}}}" if len(children) > 2 else ''
        return f"{base}{sub}{sup}"

    # --- Operators ---
    if tag == 'apply':
        op_elem, *args = list(elem)
        op_tag = get_tag(op_elem)
        op = op_map.get(op_tag, '')
        args_l = [mathml_to_latex_element(a) for a in args]
        if op == '^':
            return f"{args_l[0]}^{{{args_l[1]}}}"
        if op == 'sqrt':
            if op_tag == 'root':
                return rf"\sqrt[{args_l[1]}]{{{args_l[0]}}}"
            return rf"\sqrt{{{args_l[0]}}}"
        return f" {op} ".join(args_l)

    if tag == 'mfrac':
        return rf"\frac{{{children[0]}}}{{{children[1]}}}"
    if tag == 'msqrt':
        return rf"\sqrt{{{children[0]}}}"
    if tag == 'mroot':
        return rf"\sqrt[{children[1]}]{{{children[0]}}}"

    # --- Overscripts/Underscripts ---
    if tag == 'mover':
        if children[1].strip() in {r'\hat', '^', 'ˆ'}:
            return rf"\hat{{{children[0]}}}"
        if children[0] == r'\rightarrow':
            return rf"\overset{{{children[1]}}}{{\rightarrow}}"
        return rf"\overset{{{children[1]}}}{{{children[0]}}}"

    if tag == 'munder':
        return rf"\underset{{{children[1]}}}{{{children[0]}}}"
    if tag == 'munderover':
        base, under, over = children[0], children[1], children[2]
        if not under and not over:
            return base
        if under and not over:
            return rf"\underset{{{under}}}{{{base}}}"
        if over and not under:
            return rf"\overset{{{over}}}{{{base}}}"
        return rf"\underset{{{under}}}{{\overset{{{over}}}{{{base}}}}}"

    # --- Fenced ---
    if tag == 'mfenced':
        openf = elem.get('open', '(')
        closef = elem.get('close', ')')
        sep = elem.get('sep', ', ')
        inner = ''.join(children)

        if inner.startswith('<mtable'):
            rows = elem.findall('.//mtr')
            row_texts = []
            for row in rows:
                cells = row.findall('.//mtd') or list(row)
                cell_texts = [mathml_to_latex_element(c) for c in cells]
                row_texts.append(' & '.join(cell_texts))
            matrix_body = r' \\ '.join(row_texts)

            env_dict = {
                '(': 'pmatrix',
                '[': 'bmatrix',
                '|': 'vmatrix',
                '||': 'Vmatrix',
                '<': 'bmatrix', # Generic fallback
                '{': 'bmatrix'  # Add more as needed
            }

            env = env_dict.get((openf, closef), 'matrix')
            return rf"\begin{{{env}}}{matrix_body}\end{{{env}}}"

        # Vectors handling
        if openf + closef == '||':
            return r"\begin{bmatrix}" + inner + r"\end{bmatrix}"
        if openf == '(' and closef == ')':
            if sep:
                inner = inner.replace(sep, ' & ')
            return r"\begin{pmatrix}" + inner + r"\end{pmatrix}"
        if openf == '[' and closef == ']':
            if sep:
                inner = inner.replace(sep, ' & ')
            return r"\begin{bmatrix}" + inner + r"\end{bmatrix}"
        if openf == '|' and closef == '|':
            if sep:
                inner = inner.replace(sep, ' & ')
            return r"\begin{Vmatrix}" + inner + r"\end{Vmatrix}"

        # Fall back to general fenced
        return f"{openf}{inner}{closef}"

    # --- Tables ---
    if tag == 'mtable':
        rows = elem.findall('mtr')
        row_texts = []
        for row in rows:
            mrow = row.find('.//mrow')
            row_texts.append(mathml_to_latex_element(mrow or row))
        # Only use cases if the row looks like a system ('=' or '⇒')
        if any(('⇒' in row or '=' in row) for row in row_texts):
            return r"\begin{cases}" + r" \\".join(row_texts) + r"\end{cases}"
        elif len(row_texts) > 1:
            return r"\begin{matrix}" + r" \\".join(row_texts) + r"\end{matrix}"
        return row_texts[0]
    if tag == 'mtext':
        content = convert_persian_digits(text or ''.join(children))
        if re.fullmatch(r'[0-9a-zA-Z+\-/*=^_()\[\]{}]+', content):
            return content
        return rf"\text{{{content}}}"
    return text + ''.join(children)

def normalize_identifiers(text):
    function_patterns = ['cos', 'sin', 'tan', 'cot', 'sec', 'csc', 'log', 'ln']
    for fn in function_patterns:
        # Replace 'cosx' -> '\cos x' and similar
        text = re.sub(rf'\b{fn}([a-zA-Z])\b', rf'\\{fn} \1', text)
        # Replace 'cos(x)' -> '\cos(x)'
        text = re.sub(rf'\b{fn}\s*\(', rf'\\{fn}(', text)
    return text

def beautify_latex(expr: str) -> str:
    # 1. اصلاح دستورهای LaTeX شکسته مثل \r i g h t a r r o w → \rightarrow
    def fix_broken_commands(match):
        pieces = match.group(0).split()
        return '\\' + ''.join(pieces)[1:]  # remove duplicated backslash

    expr = re.sub(r'\\(?:\s*[a-zA-Z]+\s*){2,}', fix_broken_commands, expr)

    # 2. افزودن فاصله بعد از \sim یا \neg زمانی که پشت آن حرف هست
    expr = re.sub(r'(\\sim|\\neg)([a-zA-Z])', r'\1 \2', expr)

    # 3. فاصله‌گذاری اطراف → و ↔ و ...
    expr = re.sub(r'(\\Rightarrow|\\rightarrow|\\Leftarrow|\\leftrightarrow)', r' \1 ', expr)

    # 4. حذف فاصله‌های تکراری
    expr = re.sub(r'\s{2,}', ' ', expr)

    return expr.strip()


def clean_html_and_convert_mathml(html: str) -> str:
    tree = HTMLParser(html)

    for m in tree.root.css('math'):
        latex = mathml_to_latex_element(ET.fromstring(m.html))
        latex = beautify_latex(normalize_identifiers(latex))
        block = f"\n\n$$\n{latex}\n$$\n\n"

        container = m
        while container and not (container.tag == 'span' and 'az-formula' in container.attributes.get('class', '')):
            container = container.parent

        (container or m).replace_with(block)

    for leftover in tree.root.css('math'):
        leftover.decompose()

    text = tree.root.text(separator=' ')
    if text.count('$$') % 2 != 0:
        text = text.rstrip('$')

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return '\n'.join(lines)

