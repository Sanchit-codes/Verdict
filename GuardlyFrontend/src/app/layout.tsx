import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Guardly - Hallucination Detection Chat',
  description: 'Chat interface with real-time hallucination detection using Guardly',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50">{children}</body>
    </html>
  );
}
