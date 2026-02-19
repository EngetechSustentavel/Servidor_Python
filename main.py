from flask import Flask, request, send_file
from flask_cors import CORS
import ezdxf
import math
import os

app = Flask(__name__)
CORS(app)

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
        
        # DEFINIÇÃO DO BLOCO
        blk = doc_out.blocks.new(name='SIG_PONTO')
        blk.add_circle((0, 0), radius=0.2)
        blk.add_line((-0.3, 0), (0.3, 0))
        blk.add_line((0, -0.3), (0, 0.3))
        blk.add_attdef(tag='ID', text='ID', insert=(0.4, 0.4), dxfattribs={'height': 0.3})
        
        msp_out = doc_out.modelspace()
        pontos = msp_in.query('POINT')
        textos = msp_in.query('TEXT')
        
        # O SEGREDO: Contador inicializado fora do loop principal
        contador_p = 1
        
        for p in pontos:
            px, py = p.dxf.location.x, p.dxf.location.y
            id_final = "" # Reseta para cada ponto
            
            # Busca texto num raio de 3 metros
            encontrou_texto = False
            for t in textos:
                tx, ty = t.dxf.insert.x, t.dxf.insert.y
                dist = math.sqrt((px-tx)**2 + (py-ty)**2)
                if dist < 3.0:
                    id_final = str(t.dxf.text).strip()
                    encontrou_texto = True
                    break
            
            # Se após checar todos os textos não encontrou nada...
            if not encontrou_texto or id_final == "":
                id_final = f"P{contador_p}"
                contador_p += 1 # Incrementa para o próximo solitário
            
            # Insere no AutoCAD
            block_ref = msp_out.add_blockref('SIG_PONTO', (px, py), dxfattribs={'layer': 'VERTICES_ENGETECH'})
            block_ref.add_auto_attribs({'ID': id_final})
            
        doc_out.saveas(output_path)
        return send_file(output_path, as_attachment=True, download_name="Engetech_Master_Final.dxf")
        
    except Exception as e:
        return f"Erro: {str(e)}", 500
    finally:
        if os.path.exists(input_path): os.remove(input_path)
