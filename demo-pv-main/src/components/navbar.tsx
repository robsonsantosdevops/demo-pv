"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { Search, Menu, X, ChevronRight, ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCarrinho } from "@/components/carrinho/carrinho-context";

export function Navbar() {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [openSubmenu, setOpenSubmenu] = useState<string | null>(null);
    const [isScrolled, setIsScrolled] = useState(false);
    const { totalItens } = useCarrinho();

    // Detectar scroll
    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 10);
        };

        window.addEventListener('scroll', handleScroll);
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    const menuItems = [
        {
            name: "QUEM SOMOS",
            href: "/quem-somos",
            submenu: [
                { name: "Conheça o Poliedro Curso", href: "/quem-somos/conheca-o-poliedro-curso" },
                { name: "Unidades", href: "/quem-somos/unidades" },
                { name: "Calouros Poliedro", href: "/quem-somos/calouros-poliedro" },
                { name: "Dúvidas Frequentes", href: "https://www.poliedroeducacao.com.br/duvidas-frequentes", external: true },
            ],
        },
        {
            name: "CURSOS",
            href: "/curso",
            submenu: [
                { name: "Medicina", href: "/curso/medicina" },
                { name: "ITA", href: "/curso/ita" },
                { name: "Extensivo", href: "/curso/extensivo" },
                { name: "Meio de Ano", href: "/curso/semiextensivo" },
                { name: "Revisão", href: "/curso/revisao" },
                { name: "Online", href: "/curso/online" },
                { name: "Alojamento", href: "/curso/servicos-adicionais/alojamento" },
            ],
        },
        { name: "METODOLOGIA", href: "/metodologia" },
        { name: "APROVAÇÕES", href: "/aprovacoes" },
        {
            name: "POLIEDRO RESOLVE",
            href: "https://poliedroresolve.sistemapoliedro.com.br/#/",
            external: true
        },
        { name: "BLOG", href: "/blog" },
    ];

    const toggleSubmenu = (name: string) => {
        setOpenSubmenu(openSubmenu === name ? null : name);
    };

    return (
        <header
            className={`
                w-full sticky top-0 z-50 transition-all duration-300
                ${isScrolled
                    ? 'bg-white/60 backdrop-blur-md'
                    : 'bg-white'
                }
            `}
        >
            <div className="container mx-auto px-4 max-w-7xl">
                <div className="flex items-center justify-between h-16">
                    {/* Logo */}
                    <Link href="/" className="flex items-center">
                        <Image
                            src="/logo-poliedro-curso (2).svg"
                            alt="Poliedro Cursos"
                            width={220}
                            height={60}
                            className="h-12 w-auto object-contain"
                            priority
                        />
                    </Link>

                    {/* Desktop Navigation */}
                    <div className="hidden lg:flex items-center flex-1 justify-center">
                        <nav className="cmp-menu">
                            <ul className="flex items-center space-x-8">
                                {menuItems.map((item) => (
                                    <li key={item.name} className="relative group">
                                        {item.submenu ? (
                                            <>
                                                <button
                                                    className="flex items-center text-gray-700 hover:text-blue-600 font-medium text-sm py-2"
                                                    onClick={() => { }}
                                                >
                                                    {item.name}
                                                    <ChevronRight className="h-4 w-4 ml-1 rotate-90 group-hover:rotate-90 transition-transform" />
                                                </button>

                                                {/* Submenu dropdown */}
                                                <div className="absolute top-full left-0 w-64 bg-white/95 backdrop-blur-sm rounded-lg py-2 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
                                                    {item.submenu.map((subItem) => (
                                                        <Link
                                                            key={subItem.name}
                                                            href={subItem.href}
                                                            target={subItem.external ? "_blank" : undefined}
                                                            rel={subItem.external ? "noopener noreferrer" : undefined}
                                                            className="block px-4 py-2 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-600"
                                                        >
                                                            {subItem.name}
                                                        </Link>
                                                    ))}
                                                </div>
                                            </>
                                        ) : (
                                            <Link
                                                href={item.href}
                                                target={item.external ? "_blank" : undefined}
                                                rel={item.external ? "noopener noreferrer" : undefined}
                                                className="text-gray-700 hover:text-blue-600 font-medium text-sm py-2 inline-block"
                                            >
                                                {item.name}
                                            </Link>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </nav>
                    </div>

                    {/* Right Side Icons and Buttons */}
                    <div className="flex items-center space-x-2">
                        {/* Carrinho - Desktop */}
                        <div className="hidden lg:block relative">
                            <Link
                                href="/carrinho"
                                className="flex items-center justify-center w-10 h-10 text-gray-600 hover:text-blue-600 transition-colors relative"
                                aria-label="Carrinho"
                            >
                                <ShoppingBag className="h-5 w-5" />
                                {totalItens > 0 && (
                                    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center animate-pulse">
                                        {totalItens}
                                    </span>
                                )}
                            </Link>
                        </div>

                        {/* Search - Desktop */}
                        <div className="hidden lg:block">
                            <Link
                                href="#buscar"
                                className="flex items-center justify-center w-10 h-10 rounded-full transition-all duration-200 hover:scale-110 hover:opacity-80"
                                style={{ backgroundColor: '#E4D6CF' }}
                                aria-label="Buscar"
                            >
                                <Search className="h-5 w-5 text-gray-700" />
                            </Link>
                        </div>

                        {/* WhatsApp - Desktop */}
                        <div className="hidden lg:flex items-center space-x-2">
                            <Link
                                href="https://wa.me/551239281616"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center w-10 h-10 rounded-full transition-all duration-200 hover:scale-110 hover:opacity-80"
                                style={{ backgroundColor: '#1F9252' }}
                                aria-label="whatsapp"
                            >
                                <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12.004 2.003c-5.521 0-10 4.479-10 10 0 1.773.471 3.485 1.357 4.999L2 21.997l5.078-1.318c1.49.827 3.179 1.264 4.926 1.264 5.52 0 10-4.479 10-10 0-5.52-4.48-10-10-10zm5.657 14.486c-.239.672-1.19 1.23-1.957 1.358-.521.085-1.188.149-3.45-.74-2.893-1.136-4.757-3.92-4.902-4.099-.14-.18-1.171-1.556-1.171-2.97 0-1.414.743-2.11 1.005-2.398.262-.289.572-.361.762-.361.19 0 .38.001.547.01.193.008.424-.068.663.508.239.576.811 1.992.883 2.136.071.144.119.313.036.505-.084.192-.125.313-.25.482-.125.168-.262.375-.375.504-.125.125-.255.26-.109.51.145.25.646 1.067 1.386 1.726.954.85 1.756 1.113 2.005 1.238.25.125.396.108.542-.065.146-.173.625-.729.792-.979.168-.25.336-.209.567-.125.231.084 1.464.69 1.715.816.25.125.417.187.479.29.063.104.063.603-.176 1.255z" />
                                </svg>
                            </Link>

                            {/* Bolsas Button */}
                            <Button
                                className="text-white font-semibold px-6 rounded-full transition-all duration-200 hover:scale-105 hover:opacity-90"
                                style={{ backgroundColor: '#C9440F' }}
                                asChild
                            >
                                <Link href="/checkout">BOLSAS</Link>
                            </Button>
                        </div>

                        {/* External Link P+ */}
                        <Link
                            href="https://pmais.p4ed.com/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hidden lg:block"
                            title="P+"
                        >
                            <Image
                                src="https://cursopoliedro.com.br/app/uploads/2025/01/logo-pmais-redondo-38x38-1.svg"
                                alt="P+"
                                width={38}
                                height={38}
                                className="w-8 h-8"
                            />
                        </Link>

                        {/* Mobile Menu Button */}
                        <button
                            onClick={() => setIsMenuOpen(!isMenuOpen)}
                            className="lg:hidden p-2 text-gray-600 hover:text-blue-600 focus:outline-none"
                            aria-label={isMenuOpen ? "Fechar" : "Abrir menu"}
                        >
                            {isMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                        </button>
                    </div>
                </div>
            </div>

            {/* Mobile Menu */}
            {isMenuOpen && (
                <div className="lg:hidden fixed inset-0 bg-white z-50 overflow-y-auto">
                    <div className="p-4">
                        {/* Mobile Menu Header */}
                        <div className="flex items-center justify-between mb-6">
                            <Link href="/" onClick={() => setIsMenuOpen(false)}>
                                <Image
                                    src="https://cursopoliedro.com.br/app/themes/courses-theme/resources/assets/img/logo-poliedro-course-white.svg"
                                    alt="Poliedro Cursos"
                                    width={180}
                                    height={45}
                                    className="h-10 w-auto"
                                    loading="lazy"
                                />
                            </Link>
                            <button
                                onClick={() => setIsMenuOpen(false)}
                                className="p-2 text-gray-600 hover:text-blue-600"
                                aria-label="Fechar"
                            >
                                <X className="h-6 w-6" />
                            </button>
                        </div>

                        {/* Search in Mobile */}
                        <div className="mb-6">
                            <form action="/" method="get" className="relative">
                                <input
                                    type="text"
                                    name="s"
                                    placeholder="Busca"
                                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />
                                <button
                                    type="submit"
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600"
                                >
                                    <Search className="h-5 w-5" />
                                </button>
                            </form>
                        </div>

                        {/* Carrinho no Mobile */}
                        <Link
                            href="/carrinho"
                            className="flex items-center justify-between py-3 text-gray-700 font-medium border-b border-gray-100"
                            onClick={() => setIsMenuOpen(false)}
                        >
                            <div className="flex items-center gap-2">
                                <ShoppingBag className="h-5 w-5" />
                                <span>Carrinho</span>
                            </div>
                            {totalItens > 0 && (
                                <span className="bg-red-500 text-white text-xs rounded-full px-2 py-0.5">
                                    {totalItens} {totalItens === 1 ? 'item' : 'itens'}
                                </span>
                            )}
                        </Link>

                        {/* Mobile Menu Items */}
                        <nav className="cmp-menu__list-wrapper mt-2">
                            <ul className="space-y-2">
                                {menuItems.map((item) => (
                                    <li key={item.name} className="border-b border-gray-100 last:border-0">
                                        {item.submenu ? (
                                            <>
                                                <button
                                                    onClick={() => toggleSubmenu(item.name)}
                                                    className="flex items-center justify-between w-full py-3 text-gray-700 font-medium"
                                                >
                                                    {item.name}
                                                    <ChevronRight className={`h-5 w-5 transition-transform ${openSubmenu === item.name ? 'rotate-90' : ''}`} />
                                                </button>

                                                {openSubmenu === item.name && (
                                                    <ul className="pl-4 pb-3 space-y-2">
                                                        {item.submenu.map((subItem) => (
                                                            <li key={subItem.name}>
                                                                <Link
                                                                    href={subItem.href}
                                                                    target={subItem.external ? "_blank" : undefined}
                                                                    rel={subItem.external ? "noopener noreferrer" : undefined}
                                                                    className="block py-2 text-sm text-gray-600 hover:text-blue-600"
                                                                    onClick={() => setIsMenuOpen(false)}
                                                                >
                                                                    {subItem.name}
                                                                </Link>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                )}
                                            </>
                                        ) : (
                                            <Link
                                                href={item.href}
                                                target={item.external ? "_blank" : undefined}
                                                rel={item.external ? "noopener noreferrer" : undefined}
                                                className="block py-3 text-gray-700 font-medium hover:text-blue-600"
                                                onClick={() => setIsMenuOpen(false)}
                                            >
                                                {item.name}
                                            </Link>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </nav>

                        {/* Mobile Action Buttons */}
                        <div className="mt-6 space-y-3">
                            <Link
                                href="/checkout"
                                className="block w-full text-white font-semibold text-center py-3 rounded-full transition-all duration-200 hover:scale-105 hover:opacity-90"
                                style={{ backgroundColor: '#C9440F' }}
                                onClick={() => setIsMenuOpen(false)}
                            >
                                BOLSAS
                            </Link>

                            <Link
                                href="https://wa.me/551239281616"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center space-x-2 w-full text-white font-semibold py-3 rounded-full transition-all duration-200 hover:scale-105 hover:opacity-90"
                                style={{ backgroundColor: '#1F9252' }}
                                onClick={() => setIsMenuOpen(false)}
                            >
                                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12.004 2.003c-5.521 0-10 4.479-10 10 0 1.773.471 3.485 1.357 4.999L2 21.997l5.078-1.318c1.49.827 3.179 1.264 4.926 1.264 5.52 0 10-4.479 10-10 0-5.52-4.48-10-10-10zm5.657 14.486c-.239.672-1.19 1.23-1.957 1.358-.521.085-1.188.149-3.45-.74-2.893-1.136-4.757-3.92-4.902-4.099-.14-.18-1.171-1.556-1.171-2.97 0-1.414.743-2.11 1.005-2.398.262-.289.572-.361.762-.361.19 0 .38.001.547.01.193.008.424-.068.663.508.239.576.811 1.992.883 2.136.071.144.119.313.036.505-.084.192-.125.313-.25.482-.125.168-.262.375-.375.504-.125.125-.255.26-.109.51.145.25.646 1.067 1.386 1.726.954.85 1.756 1.113 2.005 1.238.25.125.396.108.542-.065.146-.173.625-.729.792-.979.168-.25.336-.209.567-.125.231.084 1.464.69 1.715.816.25.125.417.187.479.29.063.104.063.603-.176 1.255z" />
                                </svg>
                                <span>Atendimento via WhatsApp</span>
                            </Link>
                        </div>
                    </div>
                </div>
            )}
        </header>
    );
}