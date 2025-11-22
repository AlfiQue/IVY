# -*- coding: utf-8 -*-
from pathlib import Path
text = Path('webui/src/pages/Chat.tsx').read_text(encoding='utf-8')
print('return  s;' in text)
