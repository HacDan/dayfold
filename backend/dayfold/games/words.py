"""Small curated word lists (written for Dayfold, public domain like any word list).

Words are stored without accents and uppercased at use, so they work on any keyboard and
in the KOReader plugin.
"""

from __future__ import annotations

WORDLE: dict[str, dict[int, list[str]]] = {
    "pt": {
        4: ["amor", "bola", "casa", "dado", "fogo", "gato", "lago", "lado", "mesa", "mala", "nave", "pato", "rato", "roda", "sapo", "teia", "vela", "vida", "zero", "faca", "foca", "mapa", "nota", "onda", "pena", "rosa", "sala", "sino", "tela", "vaca", "vale", "fila", "gelo", "leao", "lixo", "luva", "meta", "muro", "neve", "olho", "pao?", "pele", "pipa", "raiz", "rede", "sede", "sopa", "tatu", "time", "urso", "vaso", "voto"],
        5: ["amigo", "banco", "barco", "beijo", "bolsa", "brisa", "cabra", "campo", "canto", "carta", "casal", "cerca", "chave", "chuva", "cinco", "clima", "cobra", "corpo", "couro", "cravo", "creme", "curso", "danca", "dente", "disco", "drama", "duelo", "falar", "farol", "festa", "fibra", "filme", "folha", "fonte", "forno", "forca", "fruta", "fundo", "garfo", "gesto", "globo", "gosto", "grama", "grupo", "hotel", "ideia", "igual", "jogar", "jovem", "lapis", "largo", "leite", "lenco", "letra", "livro", "lousa", "lugar", "magia", "manga", "marco", "massa", "metal", "metro", "milho", "moeda", "morro", "mundo", "museu", "nadar", "navio", "noite", "norte", "nuvem", "ordem", "ouvir", "padre", "palco", "papel", "parte", "pasta", "pedra", "peixe", "perto", "piano", "pilha", "placa", "plano", "poema", "ponte", "porta", "prado", "praia", "prato", "prazo", "preco", "prova", "pular", "quase", "radio", "regra", "reino", "risco", "roupa", "sabor", "salto", "samba", "selva", "senha", "sinal", "sonho", "sorte", "sopro", "tarde", "tempo", "terra", "texto", "tigre", "tinta", "toque", "total", "trigo", "turma", "valor", "vapor", "velho", "vento", "verde", "verso", "vidro", "vinho", "viola", "visao", "vista", "viver", "zebra"],
        6: ["abelha", "banana", "brilho", "cadeia", "camelo", "caneta", "cidade", "cometa", "desejo", "escola", "espaco", "futuro", "janela", "jardim", "limite", "macaco", "musica", "outono", "pintor", "quadro", "queijo", "rainha", "sapato", "tomate", "viagem", "volume"],
    },
    "en": {
        4: ["bird", "book", "cake", "door", "fish", "gold", "hand", "kite", "lamp", "leaf", "moon", "nest", "park", "rain", "ship", "snow", "star", "tree", "wind", "wolf"],
        5: ["apple", "beach", "bread", "brick", "chair", "cloud", "crane", "dance", "dream", "earth", "field", "flame", "frost", "glass", "grape", "heart", "honey", "house", "juice", "knife", "lemon", "light", "music", "night", "ocean", "paper", "piano", "plant", "quiet", "river", "round", "scale", "sheep", "smile", "stone", "storm", "sugar", "table", "tiger", "train", "voice", "water", "whale", "world", "youth", "actor", "alarm", "brave", "cabin", "candy", "chalk", "clock", "coast", "crown", "eagle", "fable", "faith", "flute", "globe", "grain", "horse", "image", "jolly", "kneel", "laser", "maple", "medal", "noble", "olive", "orbit", "pearl", "pilot", "prism", "radio", "robin", "salad", "shell", "solar", "spice", "swift", "theme", "torch", "uncle", "value", "vivid", "wheat", "zebra"],
        6: ["anchor", "bridge", "candle", "castle", "dragon", "forest", "garden", "island", "jungle", "kettle", "ladder", "magnet", "orange", "planet", "rocket", "silver", "spring", "summer", "travel", "winter"],
    },
}

# drop any accidental placeholder entries
for _lang in WORDLE.values():
    for _n, _words in _lang.items():
        _lang[_n] = sorted({w for w in _words if w.isalpha() and len(w) == _n})

WORDSEARCH_THEMES: dict[str, dict[str, list[str]]] = {
    "pt": {
        "animais": ["gato", "cachorro", "cavalo", "coelho", "girafa", "tigre", "zebra", "macaco", "baleia", "tucano", "onca", "papagaio", "tartaruga", "golfinho", "coruja", "raposa"],
        "natureza": ["floresta", "rio", "montanha", "cachoeira", "praia", "areia", "folha", "flor", "semente", "chuva", "vento", "nuvem", "pedra", "lago", "oceano"],
        "espaco": ["planeta", "estrela", "cometa", "galaxia", "orbita", "lua", "satelite", "foguete", "asteroide", "nebulosa", "marte", "jupiter", "saturno", "telescopio"],
        "cidade": ["rua", "praca", "ponte", "predio", "escola", "museu", "teatro", "mercado", "parque", "onibus", "metro", "bairro", "calcada", "esquina"],
        "cozinha": ["panela", "garfo", "colher", "prato", "forno", "arroz", "feijao", "tempero", "sal", "acucar", "farinha", "manteiga", "queijo"],
    },
    "en": {
        "animals": ["cat", "dog", "horse", "rabbit", "giraffe", "tiger", "zebra", "monkey", "whale", "toucan", "jaguar", "parrot", "turtle", "dolphin", "owl", "fox"],
        "nature": ["forest", "river", "mountain", "waterfall", "beach", "sand", "leaf", "flower", "seed", "rain", "wind", "cloud", "stone", "lake", "ocean"],
        "space": ["planet", "star", "comet", "galaxy", "orbit", "moon", "satellite", "rocket", "asteroid", "nebula", "mars", "jupiter", "saturn", "telescope"],
        "city": ["street", "square", "bridge", "tower", "school", "museum", "theater", "market", "park", "bus", "subway", "district", "sidewalk", "corner"],
        "kitchen": ["pan", "fork", "spoon", "plate", "oven", "rice", "beans", "spice", "salt", "sugar", "flour", "butter", "cheese"],
    },
}

STOPWORDS = set(
    ["a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "por", "para", "pelo", "pela", "com", "sem", "que", "se", "ao", "aos", "e", "ou", "mas", "mais", "menos", "como", "sobre", "entre", "apos", "ate", "seu", "sua", "seus", "suas", "ser", "sao", "foi", "vai", "tem", "ter", "este", "esta", "isso", "isto", "ele", "ela", "eles", "elas", "nao", "sim", "ja", "ha", "the", "of", "and", "to", "in", "on", "for", "with", "from", "by", "at", "is", "are", "was", "were", "be", "has", "have", "will", "after", "over", "into", "new", "says", "said", "about", "their", "its", "this", "that", "than", "more", "brasil"]
)
