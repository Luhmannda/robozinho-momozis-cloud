#!/usr/bin/env python3
# =====================================================================
# test_escopo.py — escopo regional dos concursos (work/escopo.py): quadro de
# apoio só no Sul e no Sudeste (com MG) ou nacional; carreiras finais em todo
# o país. Sem rede, sem estado vivo.
# USO: python3 work/testes/test_escopo.py   (imprime OK/FALHOU; sai != 0 em falha)
# =====================================================================

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import escopo  # noqa: E402

falhas = []


def confere(nome, obtido, esperado):
    if obtido == esperado:
        print("OK     ", nome)
    else:
        falhas.append(nome)
        print("FALHOU ", nome, "— obtido", repr(obtido), "esperado", repr(esperado))


APOIO = "Quadro de apoio"
CASOS_REGISTRO = [
    ({"id": "trt8_apoio", "bloco": APOIO, "linha": "TRT8 — Analista e Técnico Judiciário: edital 1/2026"}, "fora"),
    ({"id": "trf3_apoio", "bloco": APOIO, "linha": "TRF3 — Analista e Técnico Judiciário (Vunesp, Edital 01/2026): 11 vagas"}, "dentro"),
    ({"id": "dpe_pb_apoio", "bloco": APOIO, "linha": "DPE-PB — Analista e Técnico da Defensoria: Edital nº 01/2026, FCC"}, "fora"),
    ({"id": "pge_rj_apoio", "bloco": APOIO, "linha": "PGE-RJ — Analista e Técnico: autorização publicada no DOERJ"}, "dentro"),
    ({"id": "tjpb_apoio", "bloco": APOIO, "linha": "TJPB — Analista Judiciário (Edital nº 01/2026): banca FGV"}, "fora"),
    ({"id": "dpdf_apoio", "bloco": APOIO, "linha": "DPDF (Defensoria Pública do DF) — Analista (cargo não confirmado)"}, "fora"),
    ({"id": "trt4_apoio", "bloco": APOIO, "linha": "TRT4 (RS) — Analista e Técnico Judiciário: Edital nº 1/2026"}, "dentro"),
    ({"id": "mpsp_oficial", "bloco": APOIO, "linha": "MP-SP — Oficial de Promotoria I: concurso autorizado"}, "dentro"),
    ({"id": "mppa_apoio", "bloco": APOIO, "linha": "MP-PA — servidores: uma secundária diz que o órgão confirmou edital"}, "fora"),
    ({"id": "mpu_apoio", "bloco": APOIO, "linha": "MPU — Analista e Técnico: 152 vagas"}, "dentro"),
    ({"id": "tjmg_apoio", "bloco": APOIO, "linha": "TJMG — Oficial Judiciário: edital publicado"}, "dentro"),
    ({"id": "x_apoio", "bloco": APOIO, "linha": "Tribunal — Analista: edital"}, "indefinido"),
    ({"id": "tjpb_juiz", "bloco": "Magistratura Estadual", "linha": "TJPB — Juiz Substituto"}, "dentro"),
    ({"id": "dpe_ro", "bloco": "Defensor Público Estadual (DPE)", "linha": "DPE-RO — Defensor Público"}, "dentro"),
]
for reg, esperado in CASOS_REGISTRO:
    confere("registro %s" % reg["id"], escopo.registro_no_escopo(reg), esperado)

CASOS_TEXTO = [
    ("TJ-AL — Oficial de Justiça Avaliador", "fora"),
    ("TRT-MT — Analista", "fora"),
    ("TJ-PR — Contador (Fundatec)", "dentro"),
    ("TRT 15ª Região — Técnico", "dentro"),
    ("Tribunal Regional do Trabalho da 3ª Região — Analista", "dentro"),
    ("Tribunal de Justiça de Minas Gerais — Analista", "dentro"),
    ("Tribunal de Justiça do Pará — Analista", "fora"),
    ("Concurso para servidores, edital previsto para dezembro", "indefinido"),
    ("PGM Suzano/SP — Procurador", "dentro"),
    ("TRF1 — Analista Judiciário", "fora"),
    ("TRF6 — Técnico Judiciário", "dentro"),
    ("DPU — Analista", "dentro"),
]
for texto, esperado in CASOS_TEXTO:
    confere("texto %r" % texto, escopo.apoio_no_escopo(texto), esperado)

CASOS_SLUG = [
    ("tjpb26", "fora"), ("trt2sp25", "dentro"), ("dperj2026", "dentro"), ("tjsc26", "dentro"),
    ("trt8pa26", "fora"), ("mpu25", "dentro"), ("tjdft26", "fora"), ("tjmg25", "dentro"),
    # rev1 C7: regiao e ano colados, a mesma separacao do bancas.partes_slug (o SLUG_TR guloso lia trt225 como TRT22)
    ("trt225", "dentro"), ("trt22025", "dentro"), ("trt1526", "dentro"), ("trt2426", "fora"), ("trt24", "fora"),
    ("trt2025", "fora"), ("trf225", "dentro"), ("trf62025", "dentro"), ("trf5juiz26", "fora"),
]
for slug, esperado in CASOS_SLUG:
    confere("slug %s" % slug, escopo.apoio_no_escopo(slug=slug), esperado)

# as UFs exatas: trt225 = TRT2/2025 (SP); trt2025 = TRT20/2025 (SE: "025" nao e ano; TRT2 de 2025 e trt225 ou
# trt22025); trf225 = TRF2/2025 (RJ/ES)
CASOS_UF_SLUG = [("trt225", {"SP"}), ("trt22025", {"SP"}), ("trt2025", {"SE"}), ("trf225", {"RJ", "ES"}),
                 ("trt1526", {"SP"}), ("trt2", {"SP"}), ("trt12", {"SC"})]
for slug, esperado in CASOS_UF_SLUG:
    confere("ufs do slug %s" % slug, escopo.ufs_de_slug(slug), esperado)

confere("'para' preposição não vira PA",
        escopo.ufs_de_texto("Concurso para analista do TRT2"), {"SP"})

print()
if falhas:
    print("FALHOU: %d caso(s)" % len(falhas))
    sys.exit(1)
print("TODOS OK (%d casos)" % (len(CASOS_REGISTRO) + len(CASOS_TEXTO) + len(CASOS_SLUG) + len(CASOS_UF_SLUG) + 1))
