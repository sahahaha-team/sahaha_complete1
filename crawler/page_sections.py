"""Preserve headings and table rows instead of flattening every cell into text."""
from bs4 import BeautifulSoup
from chatbot.source_text import clean_source_text


def extract_sections(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'lxml')
    for node in soup.select('script,style,nav,header,footer,.gnb,.lnb,.side_menu,#footer'):
        node.decompose()
    root = soup.select_one('.cont_area, #contents, .content_area, .board_view, main, article')
    if root is None:
        return []
    title = soup.title.get_text(' ',strip=True) if soup.title else ''
    sections, heading, parts = [], title, []
    parents = {}
    tags = ['h2','h3','h4','h5','h6','p','li','tr','dt','dd']
    def flush():
        text = clean_source_text('\n'.join(parts))
        if text:
            sections.append({'heading': heading, 'text': text})
    for node in root.find_all(tags):
        # A nested list or paragraph belongs to its enclosing list item.
        if any(parent.name in ('li','tr','p') for parent in node.parents if parent is not root):
            continue
        value = node.get_text(' ',strip=True)
        if not value:
            continue
        if node.name.startswith('h'):
            flush()
            level = int(node.name[1])
            parents = {depth: label for depth, label in parents.items() if depth < level}
            parents[level] = value
            heading, parts = ' / '.join(parents.values()), []
        elif node.name == 'tr':
            cells = [c.get_text(' ',strip=True) for c in node.find_all(['th','td'],recursive=False)]
            if cells:
                parts.append(' | '.join(cells))
        else:
            parts.append(value)
    flush()
    return sections
