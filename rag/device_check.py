"""Diagnostic matériel : PyTorch voit-il la carte graphique ? (python -m rag.device_check)

BGE-M3 et le reranker utilisent automatiquement CUDA si PyTorch le voit. Sous Windows,
`pip install torch` installe la version CPU par défaut : voir README, section carte graphique."""

import json


def main() -> None:
    import torch

    info = {"torch": torch.__version__, "cuda_disponible": torch.cuda.is_available()}
    if info["cuda_disponible"]:
        p = torch.cuda.get_device_properties(0)
        info |= {"carte": p.name, "memoire_go": round(p.total_memory / 1024**3, 1), "cuda": torch.version.cuda}
    elif "+cpu" in torch.__version__:
        info["conseil"] = ("PyTorch installé en version CPU : pip uninstall -y torch puis "
                           "pip install torch --index-url https://download.pytorch.org/whl/cu128")
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
