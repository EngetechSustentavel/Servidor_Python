from flask import Flask, request, send_file
from flask_cors import CORS  # Adicionamos isso para evitar bloqueios
import ezdxf
import math
import os

app = Flask(__name__)
CORS(app) # Permite que seu site PHP converse com o Render sem travas

@app.route('/convert', methods=['POST'])
def convert():
    if 'dxf_file' not in request.files:
        return "Nenhum arquivo enviado", 400
        
    file = request.files['dxf_file']
    input_path = "temp_in.dxf"
    output_path = "temp_out.dxf"
    file.save(input_path)

    try:
        # Carrega o DXF enviado pela Engetech
        doc_in = ezdxf.readfile(input_path)
        msp_in = doc_in.modelspace()
        
        # Cria o novo DXF R2010 (estável)
        doc_out = ezdxf.new('R2010')
        
        # DEFINIÇÃO DO BLOCO SIG_PONTO (Círculo + Cruz)
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2, dxfattribs={'layer': '0'})
        blk.add_line((-0.3, 0), (0.3, 0), dxfattribs={'layer': '0'})
        blk.add_line((0, -0.3), (0, 0.3), dxfattribs={'layer': '0'})
        # Atributo que receberá o nome do vértice
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3, 'layer': '0'})
        
        msp_out = doc_out.modelspace()
        pontos = msp_in.query('POINT')
        textos = msp_in.query('TEXT')
        
        for p in pontos:
            px, py = p.dxf.location.x, p.dxf.location.y
            id_val = "P" # Padrão
            
            # Lógica de proximidade para capturar o ID correto
            for t in textos:
                tx, ty = t.dxf.insert.x, t.dxf.insert.y
                if math.sqrt((px-tx)**2 + (py-ty)**2) < 3.0:
                    id_val = t.dxf.text
                    break
            
            # INSERÇÃO DO BLOCO REAL NO AUTOCAD
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_val})
            
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Master_Final.dxf")
        
    except Exception as e:
        return f"Erro no processamento: {str(e)}", 500
    finally:
        # Limpeza de arquivos temporários para não encher o servidor
        if os.path.exists(input_path): os.remove(input_path)
