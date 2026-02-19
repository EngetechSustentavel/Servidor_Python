from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
from pyproj import Transformer
from docx import Document # Biblioteca para ler o memorial .docx

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO DE COORDENADAS SIRGAS 2000 ---
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def gms_para_decimal(gms_str, sentido):
    try:
        partes = re.findall(r"(\d+[\.,]?\d*)", gms_str)
        graus = float(partes[0].replace(',', '.'))
        minutos = float(partes[1].replace(',', '.'))
        segundos = float(partes[2].replace(',', '.'))
        decimal = graus + (minutos / 60) + (segundos / 3600)
        return -decimal if sentido in ['S', 'W', 'O'] else decimal
    except: return None

# --- ROTA 1: GEOCONVERTER (MANTER 100% OK) ---
@app.route('/convert', methods=['POST'])
def convert():
    if 'dxf_file' not in request.files: return "Erro", 400
    file = request.files['dxf_file']
    input_path, output_path = "temp_in.dxf", "temp_out.dxf"
    file.save(input_path)
    try:
        doc_in = ezdxf.readfile(input_path)
        msp_in = doc_in.modelspace()
        doc_out = ezdxf.new('R2010')
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2)
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3})
        msp_out = doc_out.modelspace()
        contador_p = 1
        for p in msp_in.query('POINT'):
            px, py = p.dxf.location.x, p.dxf.location.y
            id_f = f"P{contador_p}"
            contador_p += 1
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_f})
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Convertido.dxf")
    except Exception as e: return str(e), 500
    finally:
        if os.path.exists(input_path): os.remove(input_path)

# --- ROTA 2: GEOEXTRATOR (VERSÃO DOCX COM ATRIBUTOS) ---
@app.route('/extract_docx', methods=['POST'])
def extract_docx():
    if 'docx_file' not in request.files: return "Nenhum arquivo enviado", 400
    
    file = request.files['docx_file']
    docx_path = "temp_memorial.docx"
    file.save(docx_path)
    
    try:
        # Lendo o conteúdo do Word
        doc_word = Document(docx_path)
        texto_completo = "\n".join([para.text for para in doc_word.paragraphs])
        
        # Captura de dados (Baseada nos memoriais da Engetech)
        nomes_v = re.findall(r"RRGL-[PV]-\d+", texto_completo)
        lats = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"S)", texto_completo)
        lons = re.findall(r"(\d+°\d+'\d+[\.,]?\d*\"W)", texto_completo)
        
        vertices_utm = []
        for i in range(min(len(lats), len(lons))):
            lat_d = gms_para_decimal(lats[i], 'S')
            lon_d = gms_para_decimal(lons[i], 'W')
            x, y = transformer.transform(lon_d, lat_d)
            vertices_utm.append((x, y))

        if not vertices_utm: return "Erro: Coordenadas não encontradas no DOCX.", 400

        # Criando o DXF com Blocos e Atributos
        output_dxf = "Engetech_Extraido_Doc.dxf"
        doc_dxf = ezdxf.new('R2010')
        
        # Bloco com Atributos para o Extrator
        blk = doc_dxf.blocks.new(name='SIG_EXTRAIDO')
        blk.add_circle((0, 0), radius=0.8)
        blk.add_attdef(tag='ID', text='ID', insert=(1, 1), dxfattribs={'height': 1.2})
        
        msp = doc_dxf.modelspace()
        msp.add_lwpolyline(vertices_utm, dxfattribs={'closed': True, 'layer': 'POLIGONAL_ENGETECH', 'color': 1})
        
        for i, v in enumerate(vertices_utm):
            nome = nomes_v[i] if i < len(nomes_v) else f"V{i+1}"
            br = msp.add_blockref('SIG_EXTRAIDO', v, dxfattribs={'layer': 'VERTICES'})
            br.add_auto_attribs({'ID': nome})
            
        doc_dxf.saveas(output_dxf)
        return send_file(output_dxf, as_attachment=True, download_name="Engetech_Poligonal_Doc.dxf")
    
    except Exception as e: return f"Erro no Word: {str(e)}", 500
    finally:
        if os.path.exists(docx_path): os.remove(docx_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
