/**
 * Dev proxy : forward l'IP réelle du navigateur vers FastAPI
 * (X-Forwarded-For / X-Real-IP) pour l'audit.
 * Seule l'adresse de la socket compte : un X-Forwarded-For envoyé par le navigateur est ignoré.
 */
export default {
  '/api': {
    target: 'http://127.0.0.1:8000',
    secure: false,
    changeOrigin: true,
    xfwd: true,
    logLevel: 'warn',
    configure: (proxy) => {
      proxy.on('proxyReq', (proxyReq, req) => {
        let ip = req.socket?.remoteAddress || req.connection?.remoteAddress || '';
        if (ip.toLowerCase().startsWith('::ffff:')) {
          ip = ip.slice(7);
        }
        if (ip) {
          proxyReq.setHeader('x-forwarded-for', ip);
          proxyReq.setHeader('x-real-ip', ip);
        }
      });
    },
  },
};
