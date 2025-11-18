import streamlit as st
import pandas as pd
import json
import glob
import os
import plotly.express as px
from json import JSONDecoder

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Dashboard Sygio - Viabilidade Econômica",
    page_icon="📊",
    layout="wide"
)

# --- CSS ---
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .dataframe { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# --- LISTA DE MESES ---
MESES_ORDENADOS = ['01-Jan', '02-Fev', '03-Mar', '04-Abr', '05-Mai', '06-Jun', 
                   '07-Jul', '08-Ago', '09-Set', '10-Out', '11-Nov', '12-Dez']

# --- FUNÇÕES AUXILIARES ---

def extrair_objetos_json(texto):
    objetos = []
    decoder = JSONDecoder()
    pos = 0
    texto = texto.strip()
    if texto.startswith('['): pos = 1
    while pos < len(texto):
        while pos < len(texto) and (texto[pos].isspace() or texto[pos] in ',]'): pos += 1
        if pos >= len(texto): break
        try:
            obj, nova_pos = decoder.raw_decode(texto, pos)
            objetos.append(obj)
            pos = nova_pos
        except:
            if texto[pos:pos+2] == '][': pos += 1; continue
            pos += 1 
    return objetos

def carregar_mapa_clientes(pasta):
    caminho = os.path.join(pasta, "clientes.json")
    mapa = {} 
    if not os.path.exists(caminho): return {}

    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read()
            try: data = json.loads(conteudo)
            except: 
                try: data = json.loads(conteudo.replace('][', ','))
                except: data = {'items': extrair_objetos_json(conteudo)}
            
            lista = data.get('items', []) if isinstance(data, dict) else data
            if not isinstance(lista, list): lista = []

            for c in lista:
                if not isinstance(c, dict): continue
                cli_id = c.get('id')
                org = c.get('organizacao')
                
                cat = "Público"
                if isinstance(org, dict) and org.get('id') == 4:
                    cat = "Privado"
                
                if cli_id: 
                    mapa[cli_id] = {
                        'cat': cat,
                        'nome': c.get('nome', '').upper()
                    }
    except: pass
    return mapa

@st.cache_data(ttl=3600) 
def carregar_dados(pasta="dados_api"):
    dados_consolidados = []
    mapa_clientes = carregar_mapa_clientes(pasta)
    arquivos = glob.glob(os.path.join(pasta, "transacoes_*.json"))
    
    if arquivos:
        status_text = st.empty()
        prog_bar = st.progress(0)
        
        for i, arquivo in enumerate(arquivos):
            try:
                prog_bar.progress((i + 1) / len(arquivos))
                status_text.text(f"Lendo {os.path.basename(arquivo)}...")

                with open(arquivo, 'r', encoding='utf-8') as f:
                    raw = f.read()
                    try: conteudo = json.loads(raw)
                    except: 
                        try: conteudo = json.loads(raw.replace('][', ','))
                        except: conteudo = {'items': extrair_objetos_json(raw)}
                    
                    lista = conteudo.get('items', []) if isinstance(conteudo, dict) else conteudo
                    if not isinstance(lista, list): lista = [] if not isinstance(lista, dict) else [lista]

                    for t in lista:
                        if not isinstance(t, dict): continue
                        
                        dt_str = t.get('data_cadastro') or t.get('data_transacao')
                        valor = float(t.get('valor_bruto') or t.get('valor_total') or 0)
                        
                        if not dt_str or valor <= 0: continue
                        
                        cliente_id = t.get('cliente_id')
                        if not cliente_id and isinstance(t.get('cliente'), dict):
                            cliente_id = t['cliente'].get('id')
                        
                        info_cli = mapa_clientes.get(cliente_id, {})
                        tipo_base = info_cli.get('cat', 'Público')
                        nome_cli = info_cli.get('nome')
                        
                        if not nome_cli:
                            if isinstance(t.get('cliente'), dict):
                                nome_cli = t['cliente'].get('nome', 'Cliente Desconhecido').upper()
                            else:
                                nome_cli = f"Cliente {cliente_id}"
                        
                        dados_consolidados.append({
                            'data': dt_str,
                            'valor': valor,
                            'tipo_base': tipo_base,
                            'cliente_nome': nome_cli,
                            'cliente_id': cliente_id,
                            'credenciado_id': t.get('credenciado_id'),
                            'tem_pix': 1 if 'PIX' in str(t.get('forma_pagamento', '')).upper() else 0,
                            'taxa_adm_pct': float(t.get('taxa_administrativa_credenciado') or 0)
                        })
            except: continue
        
        status_text.empty()
        prog_bar.empty()
    
    if not dados_consolidados:
        return pd.DataFrame()

    df = pd.DataFrame(dados_consolidados)
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    df = df.dropna(subset=['data'])
    df['ano'] = df['data'].dt.year
    df['mes'] = df['data'].dt.month
    df['mes_nome'] = df['mes'].map({i+1: m for i, m in enumerate(MESES_ORDENADOS)})
    
    return df

def formatar_tabela_excel(df_pivot):
    df_final = df_pivot.reindex(columns=MESES_ORDENADOS, fill_value=0)
    df_final['Total Anual'] = df_final.sum(axis=1)
    df_final['Média Mensal'] = df_final['Total Anual'] / 12
    return df_final

# --- DASHBOARD ---
st.title("🚀 Sygio | Estudo de Viabilidade (Dados Reais)")
df_raw = carregar_dados()

if df_raw.empty:
    st.error("Sem dados.")
    st.stop()

st.sidebar.header("Filtros")
anos = sorted(df_raw['ano'].unique())
ano_sel = st.sidebar.selectbox("Ano", anos, index=len(anos)-1)
df_ano = df_raw[df_raw['ano'] == ano_sel]

if df_ano.empty: st.stop()

# --- TABELA 1 ---
st.header(f"1. Volumetria Geral ({ano_sel})")

ranking = df_ano.groupby(['cliente_id', 'cliente_nome', 'tipo_base'])['valor'].sum().reset_index()
top_pub = ranking[ranking['tipo_base'] == 'Público'].nlargest(1, 'valor')
id_top_pub = top_pub.iloc[0]['cliente_id'] if not top_pub.empty else None
nome_top_pub = top_pub.iloc[0]['cliente_nome'] if not top_pub.empty else "Nenhum"

top_priv = ranking[ranking['tipo_base'] == 'Privado'].nlargest(1, 'valor')
id_top_priv = top_priv.iloc[0]['cliente_id'] if not top_priv.empty else None
nome_top_priv = top_priv.iloc[0]['cliente_nome'] if not top_priv.empty else "Nenhum"

vol_publico_total = df_ano[df_ano['tipo_base'] == 'Público'].groupby('mes_nome')['valor'].sum()
vol_privado_total = df_ano[df_ano['tipo_base'] == 'Privado'].groupby('mes_nome')['valor'].sum()
vol_top_pub = df_ano[df_ano['cliente_id'] == id_top_pub].groupby('mes_nome')['valor'].sum()
vol_top_priv = df_ano[df_ano['cliente_id'] == id_top_priv].groupby('mes_nome')['valor'].sum()
vol_total_real = df_ano.groupby('mes_nome')['valor'].sum()

dados_tab1 = pd.DataFrame({
    f"⭐ {nome_top_pub} (Top Público)": vol_top_pub,
    "Credenciados/Clientes (Total)": vol_publico_total,
    f"⭐ {nome_top_priv} (Top Privado)": vol_top_priv,
    "Empresas Privadas (Total)": vol_privado_total
}).T

dados_tab1.loc['Volumetria Total'] = vol_total_real
df_tab1 = formatar_tabela_excel(dados_tab1)
st.dataframe(df_tab1.style.format("R$ {:,.2f}"), use_container_width=True)

fig_vol = px.bar(pd.DataFrame({'Público': vol_publico_total, 'Privado': vol_privado_total}).reset_index().melt(id_vars='mes_nome', var_name='Categoria', value_name='Valor').sort_values('mes_nome'), x='mes_nome', y='Valor', color='Categoria', title="Volume por Setor")
st.plotly_chart(fig_vol, use_container_width=True)

st.markdown("---")

# --- TABELA 2 ---
st.header("2. Detalhamento Operacional")

resumo = df_ano.groupby('mes_nome').agg({
    'valor': 'sum',
    'credenciado_id': 'nunique', 
    'cliente_id': 'nunique',
    'taxa_adm_pct': 'mean', 
    'tem_pix': 'sum', 
    'data': 'count'
}).T.reindex(columns=MESES_ORDENADOS, fill_value=0)

qtd_orgaos = df_ano[df_ano['tipo_base'] == 'Público'].groupby('mes_nome')['cliente_id'].nunique()
resumo.loc['qtd_orgaos_publicos'] = qtd_orgaos

mapa = {
    'valor': 'Volumetria Credenciado/Clientes',
    'credenciado_id': 'Quantidade de Credenciados Ativos',
    'qtd_orgaos_publicos': 'Quantidade de órgãos públicos',
    'data': 'Quantidade de transações',
    'tem_pix': 'Quantidade de Pix por cliente',
    'taxa_adm_pct': 'Taxa Média Aplicada (Credenciado)'
}
resumo = resumo.drop('cliente_id', errors='ignore').rename(index=mapa)
resumo.loc['Volumetria Credenciado/Clientes'] = vol_total_real

df_calc = resumo.T
df_calc['Média de transações por credenciado'] = df_calc.apply(lambda x: x['Quantidade de transações']/x['Quantidade de Credenciados Ativos'] if x['Quantidade de Credenciados Ativos']>0 else 0, axis=1)
df_calc['TPV Médio por credenciado'] = df_calc.apply(lambda x: x['Volumetria Credenciado/Clientes']/x['Quantidade de Credenciados Ativos'] if x['Quantidade de Credenciados Ativos']>0 else 0, axis=1)
df_calc['TPV Médio por órgão público'] = df_calc.apply(lambda x: x['Volumetria Credenciado/Clientes']/x['Quantidade de órgãos públicos'] if x['Quantidade de órgãos públicos']>0 else 0, axis=1)

df_calc['Taxa Média Negativa (Órgãos Públicos)'] = -0.04 
df_calc['Taxa Pix'] = 5.00; df_calc['Custo por Pix'] = 0.00
df_calc['Taxa Média de Aluguel de POS'] = 70.00; df_calc['Taxa Média de Mensalidade'] = 50.00; df_calc['Taxa de Adesão'] = 120.00

tab_op = df_calc.T
def calc_tot(row):
    if row.name in ['Volumetria Credenciado/Clientes', 'Quantidade de transações', 'Quantidade de Pix por cliente']: return row.sum()
    return row[row!=0].mean() if not row[row!=0].empty else 0

tab_op['Total/Média'] = tab_op.apply(calc_tot, axis=1)
st.dataframe(tab_op.style.format("{:,.2f}"), use_container_width=True)

st.markdown("---")

# --- TABELA 3 ---
st.header("3. Estimativa de Receitas")

rec = pd.DataFrame(index=tab_op.columns[:-1])
vols = tab_op.loc['Volumetria Credenciado/Clientes'][:-1]
tx = tab_op.loc['Taxa Média Aplicada (Credenciado)'][:-1]
pix = tab_op.loc['Quantidade de Pix por cliente'][:-1]
cred = tab_op.loc['Quantidade de Credenciados Ativos'][:-1]

rec['Credenciado - Taxa Administrativa'] = vols * (tx/100)
rec['Credenciado - Taxa de PIX'] = pix * 5.00
rec['Credenciado - Taxa de POS'] = cred * 70.00
rec['Total de Receitas =>'] = rec.sum(axis=1)

st.dataframe(rec.T.style.format("R$ {:,.2f}"), use_container_width=True)

# --- CORREÇÃO DO GRÁFICO AQUI ---
d_graf = rec.reset_index()
nome_coluna_mes = d_graf.columns[0]  # Pega o nome real da coluna (seja 'index' ou 'mes_nome')
d_graf['Mês'] = pd.Categorical(d_graf[nome_coluna_mes], categories=MESES_ORDENADOS, ordered=True)
d_graf = d_graf.sort_values('Mês')

fig_rec = px.area(d_graf, x='Mês', y='Total de Receitas =>', title="Receita Estimada")
st.plotly_chart(fig_rec, use_container_width=True)