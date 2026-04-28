"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCarrinho } from "@/components/carrinho/carrinho-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Trash2, Minus, Plus, ArrowLeft } from "lucide-react";
// import { Navbar } from "@/components/navbar"; ← REMOVIDO!

export default function CarrinhoPage() {
    const router = useRouter();
    const { 
        itens, 
        removerItem, 
        atualizarQuantidade, 
        limparCarrinho,
        totalPreco,
        totalParcelas,
        valorParcelaTotal
    } = useCarrinho();

    const handleFinalizarCompra = () => {
        router.push("/checkout");
    };

    if (itens.length === 0) {
        return (
            // <Navbar /> ← REMOVIDO! A navbar já vem do layout
            <div className="container mx-auto px-4 py-16 max-w-4xl">
                <div className="text-center">
                    <h1 className="text-3xl font-bold mb-4">Seu carrinho está vazio</h1>
                    <p className="text-gray-600 mb-8">
                        Explore nossos cursos e encontre o ideal para você!
                    </p>
                    <Link href="/">
                        <Button className="bg-blue-600 hover:bg-blue-700 text-white">
                            Ver Cursos
                        </Button>
                    </Link>
                </div>
            </div>
        );
    }

    return (
        // <Navbar /> ← REMOVIDO! A navbar já vem do layout
        <div className="container mx-auto px-4 py-8 max-w-6xl">
            {/* Cabeçalho */}
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-3xl font-bold">Carrinho de Compras</h1>
                <Button 
                    variant="outline" 
                    onClick={limparCarrinho}
                    className="text-red-600 border-red-200 hover:bg-red-50"
                >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Limpar Carrinho
                </Button>
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
                {/* Lista de itens */}
                <div className="lg:col-span-2 space-y-4">
                    {itens.map((item) => (
                        <Card key={item.id} className="overflow-hidden">
                            <CardContent className="p-6">
                                <div className="flex gap-4">
                                    {/* Barra colorida */}
                                    <div 
                                        className="w-2 rounded-full" 
                                        style={{ backgroundColor: item.cor }}
                                    />
                                    
                                    {/* Informações do item */}
                                    <div className="flex-1">
                                        <h3 className="text-lg font-bold" style={{ color: item.cor }}>
                                            {item.titulo}
                                        </h3>
                                        <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                                            {item.descricao}
                                        </p>
                                        
                                        <div className="flex items-center justify-between mt-4">
                                            {/* Preço */}
                                            <div>
                                                <p className="text-xl font-bold">
                                                    R$ {(item.preco * item.quantidade).toLocaleString('pt-BR')},00
                                                </p>
                                                <p className="text-xs text-gray-500">
                                                    {item.parcelas}x de R$ {item.valorParcela.toLocaleString('pt-BR')},00
                                                </p>
                                            </div>
                                            
                                            {/* Controles de quantidade */}
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    variant="outline"
                                                    size="icon"
                                                    className="h-8 w-8"
                                                    onClick={() => atualizarQuantidade(item.id, item.quantidade - 1)}
                                                >
                                                    <Minus className="h-4 w-4" />
                                                </Button>
                                                
                                                <span className="w-8 text-center font-medium">
                                                    {item.quantidade}
                                                </span>
                                                
                                                <Button
                                                    variant="outline"
                                                    size="icon"
                                                    className="h-8 w-8"
                                                    onClick={() => atualizarQuantidade(item.id, item.quantidade + 1)}
                                                >
                                                    <Plus className="h-4 w-4" />
                                                </Button>
                                                
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-8 w-8 text-red-600 hover:text-red-700"
                                                    onClick={() => removerItem(item.id)}
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                {/* Resumo do pedido */}
                <div className="lg:col-span-1">
                    <Card>
                        <CardContent className="p-6">
                            <h2 className="text-xl font-bold mb-4">Resumo do Pedido</h2>
                            
                            <div className="space-y-3 mb-6">
                                <div className="flex justify-between">
                                    <span className="text-gray-600">Subtotal:</span>
                                    <span className="font-medium">R$ {totalPreco.toLocaleString('pt-BR')},00</span>
                                </div>
                                
                                <div className="flex justify-between">
                                    <span className="text-gray-600">Parcelamento:</span>
                                    <span className="font-medium">{totalParcelas}x</span>
                                </div>
                                
                                <div className="flex justify-between">
                                    <span className="text-gray-600">Valor das parcelas:</span>
                                    <span className="font-medium">
                                        R$ {valorParcelaTotal.toLocaleString('pt-BR')},00
                                    </span>
                                </div>
                                
                                <div className="border-t pt-3">
                                    <div className="flex justify-between font-bold text-lg">
                                        <span>Total:</span>
                                        <span className="text-blue-600">
                                            R$ {totalPreco.toLocaleString('pt-BR')},00
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <Button 
                                className="w-full bg-green-600 hover:bg-green-700 text-white py-6 text-lg"
                                onClick={handleFinalizarCompra}
                            >
                                Finalizar Compra
                            </Button>

                            <Link 
                                href="/" 
                                className="flex items-center justify-center gap-2 mt-4 text-gray-600 hover:text-blue-600"
                            >
                                <ArrowLeft className="h-4 w-4" />
                                Continuar comprando
                            </Link>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}