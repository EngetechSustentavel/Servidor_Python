from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import ezdxf
import math
import os
import re
from pyproj import Transformer

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO DE COORDENADAS (SIRGAS 2000 / UTM 24S) ---
# Usamos EPSG:4674 para SIRGAS 2000 Geográfico e EPSG:31984 para UTM 24S (Bahia/Nordeste)
transformer = Transformer.from_crs("epsg:4674", "epsg:31984", always_xy=True)

def converter_para_utm(lat, lon):
    try:
        return transformer.transform(lon, lat)
    except Exception:
        return None

# --- ROTA 1: GEOCONVERTER (FERRAMENTA DE CONVERSÃO DE DXF) ---
@app.route('/convert', methods=['POST'])
def convert():
    if 'dxf_file' not in request.files:
        return "Nenhum arquivo enviado", 400
    
    file = request.files['dxf_file']
    input_path = "temp_in.dxf"
    output_path = "temp_out.dxf"
    file.save(input_path)

    try:
        doc_in = ezdxf.readfile(input_path)
        msp_in = doc_in.modelspace()
        doc_out = ezdxf.new('R2010')
        
        # DEFINIÇÃO DO BLOCO SIG_PONTO
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2)
        blk.add_line((-0.3, 0), (0.3, 0))
        blk.add_line((0, -0.3), (0, 0.3))
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3})
        
        msp_out = doc_out.modelspace()
        pontos = msp_in.query('POINT')
        textos = msp_in.query('TEXT')
        
        contador_p = 1
        for p in pontos:
            px, py = p.dxf.location.x, p.dxf.location.y
            id_final = ""
            encontrou_texto = False
            for t in textos:
                tx, ty = t.dxf.insert.x, t.dxf.insert.y
                if math.sqrt((px-tx)**2 + (py-ty)**2) < 3.0:
                    id_final = str(t.dxf.text).strip()
                    encontrou_texto = True
                    break
            
            if not encontrou_texto or id_final == "":
                id_final = f"P{contador_p}"
                contador_p += 1
            
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_final})
            
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Convertido.dxf")
    except Exception as e:
        return f"Erro no Geoconverter: {str(e)}", 500
    finally:
        if os.path.exists(input_path): os.remove(input_path)

# --- ROTA 2: GEOEXTRATOR (EXTRAÇÃO DE TEXTO PARA POLIGONAL CAD) ---
@app.route('/extract_text', methods=['POST'])
def extract_text():
    data = request.get_json()
    texto = data.get('texto', '')
    
    # REGEX FLEXÍVEL: Captura números formatados (1.234.567,89 ou -14.1234)
    padrao = re.findall(r"(-?\d[\d\.]*?\d,\d+|-?\d+\.\d+)", texto)
    
    vertices = []
    temp_coords = []
    
    for num in padrao:
        # Normaliza para o padrão Python (float)
        limpo = float(num.replace('.', '').replace(',', '.')) if ',' in num else float(num)
        temp_coords.append(limpo)
    
    # Agrupa em pares (X, Y)
    for i in range(0, len(temp_coords) - 1, 2):
        x, y = temp_coords[i], temp_coords[i+1]
        
        # Se for Lat/Long (valores pequenos), converte para UTM SIRGAS 2000
        if abs(x) < 180 and abs(y) < 180:
            utm = converter_para_utm(x, y) # assume x=lat, y=lon
            if utm: vertices.append(utm)
        else:
            vertices.append((x, y))

    if not vertices:
        return "Erro: Nenhuma coordenada identificada no texto.", 400

    output_path = "Engetech_Extracao.dxf"
    # Criamos o DXF forçando R2010 e declarando Layers para evitar erro de abertura
    doc = ezdxf.new('R2010')
    doc.layers.new('POLIGONAL_ENGETECH', dxfattribs={'color': 1}) # Vermelho
    doc.layers.new('VERTICES', dxfattribs={'color': 2})           # Amarelo
    
    msp = doc.modelspace()
    
    # Adiciona a poligonal fechada
    msp.add_lwpolyline(vertices, dxfattribs={'closed': True, 'layer': 'POLIGONAL_ENGETECH'})
    
    # Adiciona identificação nos vértices
    for i, v in enumerate(vertices):
        msp.add_circle(v, radius=0.8, dxfattribs={'layer': 'VERTICES'})
        txt = msp.add_text(f"V{i+1}", dxfattribs={'height': 1.2, 'layer': 'VERTICES'})
        txt.set_placement((v[0] + 0.5, v[1] + 0.5))
    
    doc.saveas(output_path)
    return send_file(output_path, as_attachment=True, download_name="Engetech_Poligonal_Extraida.dxf")

if __name__ == '__main__':
    # O Render utiliza a porta 10000 por padrão para serviços web
    app.run(host='0.0.0.0', port=10000)
