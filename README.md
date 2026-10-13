# Calculadora de Paredes Estruturais

Dimensionamento de paredes de concreto armado à flexo-compressão, flexo-tração,
cortante e esforço normal pela **NBR 6118:2026** e pelo **ACI 318-25**, com as
equações usadas e a metodologia escolhida pela geometria. Resultados em
português e inglês.

## Estado

| Etapa | Conteúdo | Situação |
| --- | --- | --- |
| 1 | Entrada, validações, combinações e classificação da metodologia | pronta |
| 2 | Seção por fibras e diagrama de interação | pronta |
| 3 | NBR 6118 completa | pronta |
| 4 | ACI 318 completo | pronta |
| 5 | Interface Streamlit e memorial para download | pronta |
| 6 | Validação com exemplos de literatura | a fazer |

## Convenções

- Seção no plano X (horizontal) × Y (vertical); a altura da parede segue Z.
- `bx` é a largura em X e `by` a profundidade em Y (cm); `hw` é a altura livre (m).
- Mx positivo comprime a face inferior; My positivo comprime a face direita.
- Normal de compressão é positiva.
- Esforços de entrada são característicos, separados em permanente (G), variável (Q) e vento (W).

## Uso rápido

```python
from calculadora_parede.entrada import Parede, Geometria, Materiais, Acoes, Esforcos, validar
from calculadora_parede.combinacoes import combinacoes_nbr, combinacoes_aci
from calculadora_parede.classificacao import tipo_elemento, regime

parede = Parede(
    Geometria(bx=300, by=20, hw=3.0),
    Materiais(fck=30),
    Acoes(G=Esforcos(N=800, My=150), Q=Esforcos(N=300, My=60), W=Esforcos(My=200, Vx=80)),
)
print(validar(parede))
print(tipo_elemento(parede).texto.pt)
print(regime(parede).texto.pt)
for c in combinacoes_nbr(parede):
    print(c.nome, c.expressao, c.esforcos)
```

## Interface web

No seu computador (Python 3.10 ou mais novo):

```
pip install -r requirements.txt
streamlit run app.py
```

Na internet, pelo Streamlit Community Cloud (gratuito):

1. Suba todos os arquivos desta pasta para o repositório no GitHub (Add file → Upload files).
2. Entre em https://share.streamlit.io com a sua conta do GitHub.
3. Clique em **Create app**, escolha o repositório, o branch `main` e o arquivo `app.py`, e clique em **Deploy**.

## Testes

```
pip install -e .[dev]
pytest
```
