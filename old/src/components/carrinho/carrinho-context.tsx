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
    valorParcelaTotal: number; // valor total POR PARCELA (soma das parcelas de todos os itens)
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

    // Calcular totais usando useMemo para evitar recálculos desnecessários
    const totais = useMemo(() => {
        const totalItens = itens.reduce((acc, item) => acc + item.quantidade, 0);
        
        const totalPreco = itens.reduce(
            (acc, item) => acc + item.preco * item.quantidade,
            0
        );
        
        // CORRIGIDO: Pega o MAIOR número de parcelas entre os itens
        const totalParcelas = Math.max(...itens.map(item => item.parcelas), 0);
        
        // CORRIGIDO: Calcula o valor total POR PARCELA
        // Para cada item: (valor da parcela * quantidade) mas só considera se o item tiver o número máximo de parcelas
        const valorParcelaTotal = itens.reduce((acc, item) => {
            // Se o item tem o mesmo número de parcelas que o totalParcelas, soma
            // Se tem menos, significa que já está pago em menos vezes, então não entra no cálculo
            if (item.parcelas === totalParcelas) {
                return acc + (item.valorParcela * item.quantidade);
            }
            return acc;
        }, 0);

        // CORRIGIDO: Versão alternativa - calcula baseado no preço total
        const valorParcelaTotalAlternativo = totalParcelas > 0 ? totalPreco / totalParcelas : 0;

        console.log('🧮 Cálculo de parcelas:', {
            totalPreco,
            totalParcelas,
            valorParcelaTotal,
            valorParcelaTotalAlternativo,
            itens: itens.map(i => ({
                nome: i.titulo,
                parcelas: i.parcelas,
                valorParcela: i.valorParcela,
                quantidade: i.quantidade,
                totalItem: i.preco * i.quantidade
            }))
        });

        return {
            totalItens,
            totalPreco,
            totalParcelas,
            valorParcelaTotal: valorParcelaTotalAlternativo // Usando a alternativa que é mais precisa
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