import sys
import re
from bs4 import BeautifulSoup, NavigableString

def clean_text(text):
    # Remove multiple spaces but preserve single spaces
    text = re.sub(r'[ 	]+', ' ', text)
    # Remove multiple newlines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def process_element_content(element):
    """Recursively process element content to handle inline tags like <a> and <code>."""
    parts = []
    for child in element.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif child.name == 'a':
            link_text = child.get_text(strip=True)
            href = child.get('href', '')
            # Clean up tracking links if they are Google redirect links
            if 'google.com/url?sa=E&q=' in href:
                match = re.search(r'q=([^&]+)', href)
                if match:
                    from urllib.parse import unquote
                    href = unquote(match.group(1))
            parts.append(f"[{link_text}]({href})")
        elif child.name == 'code':
            parts.append(f"`{child.get_text(strip=True)}`")
        elif child.name == 'b' or child.name == 'strong':
            parts.append(f"**{process_element_content(child)}**")
        elif child.name == 'i' or child.name == 'em':
            parts.append(f"*{process_element_content(child)}*")
        elif child.name == 'span':
            parts.append(process_element_content(child))
        else:
            # Fallback for other tags
            parts.append(child.get_text())
    
    return "".join(parts)

def html_to_clean_md(html_path, md_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'lxml')
    
    # Remove KaTeX internal structures that cause spacing issues
    for katex in soup.find_all(class_='katex'):
        mathml = katex.find(class_='katex-mathml')
        if mathml:
            mathml.decompose()
    
    md_lines = []
    elements = soup.find_all(['div', 'table', 'pre'])
    processed_ids = set()

    for element in elements:
        if id(element) in processed_ids:
            continue
            
        classes = element.get('class', [])
        if not classes:
            classes = []

        if 'paragraph' in classes:
            # Mark children
            for child in element.find_all(['div', 'table', 'pre']):
                processed_ids.add(id(child))
            
            text = process_element_content(element)
            text = clean_text(text)
            
            if not text:
                continue

            is_list = 'list' in classes or text.startswith('•') or text.startswith('- ') or re.match(r'^\d+\.', text)
            
            if is_list:
                if text.startswith('•'):
                    text = '- ' + text[1:].strip()
                # If the previous line was not a list item, add a newline
                if md_lines and not (md_lines[-1].startswith('- ') or re.match(r'^\d+\.', md_lines[-1])):
                    md_lines.append("")
                md_lines.append(text)
            else:
                # If the previous line was a list item, add a newline
                if md_lines and (md_lines[-1].startswith('- ') or re.match(r'^\d+\.', md_lines[-1])):
                    md_lines.append("")
                
                if 'heading1' in classes:
                    md_lines.append(f"\n# {text}\n")
                elif 'heading2' in classes:
                    md_lines.append(f"\n## {text}\n")
                elif 'heading3' in classes:
                    md_lines.append(f"\n### {text}\n")
                else:
                    md_lines.append(text + "\n")
        
        elif element.name == 'table':
            for child in element.find_all(['div', 'table', 'pre']):
                processed_ids.add(id(child))
                
            rows = []
            for tr in element.find_all('tr'):
                cells = [clean_text(td.get_text(strip=True)) for td in tr.find_all(['td', 'th'])]
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            
            if rows:
                md_lines.append("")
                md_lines.append(rows[0])
                num_columns = rows[0].count('|') - 1
                md_lines.append("| " + " | ".join(['---'] * num_columns) + " |")
                md_lines.extend(rows[1:])
                md_lines.append("")

        elif element.name == 'pre':
            for child in element.find_all(['div', 'table', 'pre']):
                processed_ids.add(id(child))
                
            code_tag = element.find('code')
            code_text = code_tag.get_text() if code_tag else element.get_text()
            md_lines.append(f"\n```\n{code_text.strip()}\n```\n")

    final_md = "\n".join(md_lines)
    # Fix spacing
    final_md = re.sub(r'\n{3,}', '\n\n', final_md)
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(final_md.strip() + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/clean_html_docs.py input.html output.md")
    else:
        html_to_clean_md(sys.argv[1], sys.argv[2])