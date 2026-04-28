"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";

// Tipo para o item do carrinho
export interface CarrinhoItem {
    id: string;
    titulo: string;
    descricao: string;
    preco: number;
    parcelas: number;
    valorParcela: number; // valor de cada parcela INDIVIDUAL do item
    cor: string;
    quantidade: number;
}

interface CarrinhoContextType {
    itens: CarrinhoItem[];
    adicionarItem: (item: Omit<CarrinhoItem, "quantidade">) => void;
    removerItem: (id: string) => void;
    atualizarQuantidade: (id: string, quantidade: number) => void;
    limparCarrinho: () => void;
    totalItens: number;
    totalPreco: number;
    totalParcelas: number;
    valorParcelaTotal: number; // valor POR PARCELA (total / parcelas)
}

const CarrinhoContext = createContext<CarrinhoContextType | undefined>(undefined);

export function CarrinhoProvider({ children }: { children: React.ReactNode }) {
    const [itens, setItens] = useState<CarrinhoItem[]>([]);
    const [isLoaded, setIsLoaded] = useState(false);

    // Carregar carrinho do localStorage apenas uma vez na montagem
    useEffect(() => {
        const carregarCarrinho = () => {
            try {
                const carrinhoSalvo = localStorage.getItem("carrinho");
                if (carrinhoSalvo) {
                    const itensParseados = JSON.parse(carrinhoSalvo);
                    setItens(itensParseados);
                }
            } catch (error) {
                console.error("Erro ao carregar carrinho:", error);
            } finally {
                setIsLoaded(true);
            }
        };

        carregarCarrinho();
    }, []);

    // Salvar carrinho no localStorage quando mudar, mas apenas após carregar
    useEffect(() => {
        if (isLoaded) {
            localStorage.setItem("carrinho", JSON.stringify(itens));
        }
    }, [itens, isLoaded]);

    const adicionarItem = useCallback((novoItem: Omit<CarrinhoItem, "quantidade">) => {
        setItens(prev => {
            const itemExistente = prev.find(item => item.id === novoItem.id);
            
            if (itemExistente) {
                return prev.map(item =>
                    item.id === novoItem.id
                        ? { ...item, quantidade: item.quantidade + 1 }
                        : item
                );
            } else {
                return [...prev, { ...novoItem, quantidade: 1 }];
            }
        });
    }, []);

    const removerItem = useCallback((id: string) => {
        setItens(prev => prev.filter(item => item.id !== id));
    }, []);

    const atualizarQuantidade = useCallback((id: string, quantidade: number) => {
        if (quantidade <= 0) {
            removerItem(id);
            return;
        }
        
        setItens(prev =>
            prev.map(item =>
                item.id === id ? { ...item, quantidade } : item
            )
        );
    }, [removerItem]);

    const limparCarrinho = useCallback(() => {
        setItens([]);
    }, []);

    // Calcular totais de forma SIMPLES e CORRETA
    const totais = useMemo(() => {
        // Total de itens (soma das quantidades)
        const totalItens = itens.reduce((acc, item) => acc + item.quantidade, 0);
        
        // Preço total (soma de preço × quantidade)
        const totalPreco = itens.reduce(
            (acc, item) => acc + item.preco * item.quantidade,
            0
        );
        
        // Número de parcelas (maior entre os itens)
        const totalParcelas = itens.length > 0 
            ? Math.max(...itens.map(item => item.parcelas)) 
            : 0;
        
        // Valor por parcela (total ÷ parcelas) - SIMPLES!
        const valorParcelaTotal = totalParcelas > 0 
            ? totalPreco / totalParcelas 
            : 0;

        console.log('🧮 Carrinho - Resumo:', {
            itens: itens.map(i => ({
                produto: i.titulo,
                qtd: i.quantidade,
                precoUnit: i.preco,
                subtotal: i.preco * i.quantidade,
                parcelasItem: i.parcelas
            })),
            totalItens,
            totalPreco,
            totalParcelas,
            valorParcelaTotal: Number(valorParcelaTotal.toFixed(2))
        });

        return {
            totalItens,
            totalPreco,
            totalParcelas,
            valorParcelaTotal
        };
    }, [itens]);

    return (
        <CarrinhoContext.Provider
            value={{
                itens,
                adicionarItem,
                removerItem,
                atualizarQuantidade,
                limparCarrinho,
                ...totais
            }}
        >
            {children}
        </CarrinhoContext.Provider>
    );
}

export function useCarrinho() {
    const context = useContext(CarrinhoContext);
    if (context === undefined) {
        throw new Error("useCarrinho deve ser usado dentro de CarrinhoProvider");
    }
    return context;
}