"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ShoppingCart, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useCarrinho } from "@/components/carrinho/carrinho-context";

interface CursoCardProps {
  id: string; // ← ADICIONADO
  titulo: string;
  descricao: string;
  inicio: string;
  colecao: string;
  badges: string[];
  cor: string;
  preco: number; // ← ADICIONADO
  parcelas: number; // ← ADICIONADO
}

export function CursoCard({ 
  id,
  titulo, 
  descricao, 
  inicio, 
  colecao, 
  badges, 
  cor,
  preco, // ← NOVO
  parcelas // ← NOVO
}: CursoCardProps) {
  const { adicionarItem } = useCarrinho();
  const valorParcela = preco / parcelas;

  const handleComprar = (e: React.MouseEvent) => {
    e.preventDefault(); // Previne navegação
    e.stopPropagation();
    
    adicionarItem({
      id,
      titulo,
      descricao,
      preco,
      parcelas,
      valorParcela,
      cor
    });
    
    // Feedback visual opcional
    const button = e.currentTarget;
    button.classList.add('scale-95', 'opacity-80');
    setTimeout(() => {
      button.classList.remove('scale-95', 'opacity-80');
    }, 200);
  };

  return (
    <Card className="h-full flex flex-col hover:shadow-lg transition-shadow rounded-2xl overflow-hidden border-gray-200 relative group">
      {/* Faixa superior colorida */}
      <div
        className="absolute top-0 left-0 right-0 h-2 transition-all group-hover:h-3"
        style={{ backgroundColor: cor }}
      />

      <CardHeader className="pb-2 pt-4">
        <CardTitle 
          className="text-xl font-bold"
          style={{ 
            fontFamily: 'Ubuntu, sans-serif',
            color: cor,
          }}
        >
          {titulo}
        </CardTitle>
        <p 
          className="text-sm mt-1 line-clamp-3"
          style={{ 
            fontFamily: 'Ubuntu, sans-serif',
            color: 'rgb(60, 60, 60)',
            lineHeight: '1.5'
          }}
        >
          {descricao}
        </p>
      </CardHeader>

      <CardContent className="grow space-y-3">
        <div>
          <p 
            className="text-xs"
            style={{ 
              fontFamily: 'Ubuntu, sans-serif',
              color: 'rgb(60, 60, 60)',
              lineHeight: '1.5'
            }}
          >
            <span className="font-medium">Início previsto:</span> {inicio}
          </p>
          <p 
            className="text-xs mt-1"
            style={{ 
              fontFamily: 'Ubuntu, sans-serif',
              color: 'rgb(60, 60, 60)',
              lineHeight: '1.5'
            }}
          >
            <span className="font-medium">Coleção:</span> {colecao}
          </p>
        </div>
        
        <div>
          <p 
            className="text-xs font-medium mb-2"
            style={{ 
              fontFamily: 'Ubuntu, sans-serif',
              color: 'rgb(60, 60, 60)'
            }}
          >
            Simulados:
          </p>
          <div className="flex flex-wrap gap-2">
            {badges.map((badge, index) => (
              <Badge 
                key={index} 
                variant="outline" 
                className="text-xs font-normal px-3 py-1"
                style={{ 
                  fontFamily: 'Ubuntu, sans-serif',
                  borderColor: cor,
                  color: cor,
                  backgroundColor: 'white'
                }}
              >
                {badge}
              </Badge>
            ))}
          </div>
        </div>

        {/* Preço - NOVO */}
        <div className="pt-2 border-t border-gray-100">
          <p className="text-xs text-gray-500">a partir de</p>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold" style={{ color: cor }}>
              R$ {preco.toLocaleString('pt-BR')},00
            </span>
            <span className="text-xs text-gray-500">à vista</span>
          </div>
          <p className="text-xs text-gray-500">
            ou {parcelas}x de R$ {valorParcela.toLocaleString('pt-BR')},00
          </p>
        </div>
      </CardContent>

      <CardFooter className="flex flex-col gap-2 pt-2">
        {/* Botão Comprar - NOVO */}
        <Button 
          className="w-full text-white font-medium py-2 text-sm rounded-lg hover:opacity-90 transition-all flex items-center justify-center gap-2"
          style={{ 
            fontFamily: 'Ubuntu, sans-serif',
            backgroundColor: cor,
            border: 'none'
          }}
          onClick={handleComprar}
        >
          <ShoppingCart className="h-4 w-4" />
          COMPRAR
        </Button>

        {/* Botão Matricular - Existente */}
        <Link href="/checkout" className="w-full">
          <Button 
            variant="outline"
            className="w-full text-gray-700 font-medium py-2 text-sm rounded-lg hover:bg-gray-50 transition-opacity flex items-center justify-center gap-2 border-gray-300"
          >
            MATRICULE-SE JÁ
            <ArrowRight className="h-4 w-4" strokeWidth={2} />
          </Button>
        </Link>
      </CardFooter>
    </Card>
  );
}