"""
Bateria de Testes do Gerenciador de Cesto Ao Vivo: Inserção, Permanência e Retirada (STR)
Projeto: SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Valida a histerese temporal e a garantia de que o carrinho reflete estritamente
o que está fisicamente presente no campo de visão da câmera em tempo real.
"""

import time
from cart_manager import GerenciadorCarrinhoAoVivo

def testar_histerese_e_fluxo_ao_vivo():
    print("=" * 65)
    print(" TESTE DE FLUXO AO VIVO: MONITORAMENTO DE CESTO POR VISÃO")
    print("=" * 65)

    # Inicializa com confirmação em 2 frames e tolerância de ausência de 0.2s para o teste
    mgr = GerenciadorCarrinhoAoVivo(confirm_frames=2, absence_timeout=0.2)

    # 1. Estado Inicial
    print("[Passo 1] Verificando cesto vazio...")
    res = mgr.obter_resumo()
    assert res["total_itens"] == 0 and res["valor_total"] == 0, "Cesto deveria iniciar vazio"
    print("  -> Cesto vazio confirmado.")

    # 2. Inserção de 1 Garrafa de Água (Frame 1: ainda não confirmado)
    print("[Passo 2] Garrafa entra no campo de visão (Frame 1)...")
    det_garrafa = [{"label": "bottle", "conf": 0.92, "box": (50, 50, 100, 180)}]
    ev1 = mgr.atualizar_inventario_ao_vivo(det_garrafa)
    assert len(ev1) == 0, "Não deve adicionar no primeiro frame (exige 2 frames de confirmação)"
    assert mgr.obter_resumo()["total_itens"] == 0
    print("  -> Frame 1 suprimido pela histerese de confirmação (anti-ruído).")

    # 3. Confirmação da Garrafa (Frame 2: confirmado!)
    print("[Passo 3] Garrafa permanece no campo de visão (Frame 2)...")
    ev2 = mgr.atualizar_inventario_ao_vivo(det_garrafa)
    assert len(ev2) == 1 and ev2[0]["tipo"] == "REGISTRADO", "Garrafa deve ser REGISTRADA"
    res2 = mgr.obter_resumo()
    assert res2["total_itens"] == 1
    assert res2["valor_total"] == 3.50
    print(f"  -> Garrafa adicionada ao cesto com sucesso! Total: R$ {res2['valor_total']:.2f}")

    # 4. Permanência do item (Frames subsequentes: não gera duplicatas)
    print("[Passo 4] Garrafa continua presente no cesto...")
    for _ in range(5):
        ev_cont = mgr.atualizar_inventario_ao_vivo(det_garrafa)
        assert len(ev_cont) == 0, "Item presente não deve ser duplicado"
    assert mgr.obter_resumo()["total_itens"] == 1
    print("  -> Cesto estável: nenhum item duplicado.")

    # 5. Adiciona um Copo junto com a Garrafa (2 itens visíveis simultâneos)
    print("[Passo 5] Copo é inserido no cesto junto à garrafa...")
    det_ambos = [
        {"label": "bottle", "conf": 0.90, "box": (50, 50, 100, 180)},
        {"label": "cup", "conf": 0.88, "box": (150, 60, 210, 160)}
    ]
    mgr.atualizar_inventario_ao_vivo(det_ambos) # Frame 1 do copo
    ev_ambos = mgr.atualizar_inventario_ao_vivo(det_ambos) # Frame 2 do copo (confirmado)
    assert any(e["tipo"] == "REGISTRADO" and e["produto"]["id"] == "PROD-002" for e in ev_ambos)
    res_ambos = mgr.obter_resumo()
    assert res_ambos["total_itens"] == 2
    assert res_ambos["valor_total"] == 18.50
    print(f"  -> Copo confirmado no cesto! Total: 2 itens (R$ {res_ambos['valor_total']:.2f})")

    # 6. Adiciona Smartphone junto no cesto (3 itens simultâneos)
    print("[Passo 6] Smartphone é inserido no cesto (3 produtos ao vivo)...")
    det_tres = [
        {"label": "bottle", "conf": 0.90, "box": (50, 50, 100, 180)},
        {"label": "cup", "conf": 0.88, "box": (150, 60, 210, 160)},
        {"label": "cell phone", "conf": 0.94, "box": (220, 60, 270, 150)}
    ]
    mgr.atualizar_inventario_ao_vivo(det_tres) # Frame 1 do celular
    ev_tres = mgr.atualizar_inventario_ao_vivo(det_tres) # Frame 2 (confirmado)
    assert any(e["tipo"] == "REGISTRADO" and e["produto"]["id"] == "PROD-003" for e in ev_tres)
    res_tres = mgr.obter_resumo()
    assert res_tres["total_itens"] == 3
    assert res_tres["valor_total"] == 1268.50
    print(f"  -> Smartphone confirmado no cesto! Total: 3 itens (R$ {res_tres['valor_total']:.2f})")

    # 7. Oclusão transitória da mão (Copo não detectado por 1 frame < timeout)
    print("[Passo 7] Simula mão do cliente ocluindo o copo momentaneamente...")
    ev_oclusao = mgr.atualizar_inventario_ao_vivo([det_tres[0], det_tres[2]])
    assert len(ev_oclusao) == 0, "Tolerância de ausência não deve remover o item imediatamente"
    assert mgr.obter_resumo()["total_itens"] == 3, "Item permanece no cesto durante a tolerância de ausência"
    print("  -> Tolerância anti-oclusão funcionou: copo mantido no cesto.")

    # 8. Retirada definitiva do Copo (ausência além do timeout)
    print("[Passo 8] Copo retirado do cesto (ausência permanente > 0.2s)...")
    time.sleep(0.25)
    ev_removido = mgr.atualizar_inventario_ao_vivo([det_tres[0], det_tres[2]])
    assert any(e["tipo"] == "REMOVIDO" and e["produto"]["id"] == "PROD-002" for e in ev_removido)
    res_removido = mgr.obter_resumo()
    assert res_removido["total_itens"] == 2
    assert res_removido["valor_total"] == 1253.50
    print(f"  -> Copo removido automaticamente! Total restante: 2 itens (R$ {res_removido['valor_total']:.2f})")

    # 9. Retirada do Smartphone e da Garrafa (Cesto fica vazio)
    print("[Passo 9] Celular e Garrafa retirados do cesto...")
    time.sleep(0.25)
    ev_vazio = mgr.atualizar_inventario_ao_vivo([])
    res_vazio = mgr.obter_resumo()
    assert res_vazio["total_itens"] == 0
    assert res_vazio["valor_total"] == 0.00
    print(f"  -> Itens removidos automaticamente! Cesto zerado: R$ {res_vazio['valor_total']:.2f}")

    print("\n" + "=" * 65)
    print("  TESTE DE FLUXO AO VIVO FINALIZADO COM 100% DE SUCESSO! ✅")
    print("=" * 65)

if __name__ == "__main__":
    testar_histerese_e_fluxo_ao_vivo()
