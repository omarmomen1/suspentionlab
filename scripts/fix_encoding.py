import codecs

path = r"C:\Users\omaar\Downloads\project\frontend2\app\quarter-car\page.tsx"
with codecs.open(path, "r", "utf-8") as f:
    text = f.read()

# Fix broken utf-8 sequences that look like mojibake
text = text.replace("Â·", "·")
text = text.replace("ÃƒÂ‚Ã‚Â¸", "·")
text = text.replace("Ã‚Â¸", "·")
text = text.replace("ÃƒÂƒÃ¢Â€ÂšÃƒÂ‚Ã‚Â¸", "·")
text = text.replace("ÃƒÂ‚", "")

with codecs.open(path, "w", "utf-8") as f:
    f.write(text)
print("Encoding fixed")
