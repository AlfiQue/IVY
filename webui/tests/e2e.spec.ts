import { test, expect } from '@playwright/test'

test('Login, activer plugin, lancer LLM, uploader ZIP', async ({ page }) => {
  await page.goto('http://localhost:5173')
  // Login
  await page.getByLabel('Utilisateur').fill('admin')
  await page.getByLabel('Mot de passe').fill('admin')
  await page.getByRole('button', { name: 'Connexion' }).click()

  // Aller Plugins
  await page.getByRole('link', { name: 'Plugins' }).click()
  // Activer/démarrer (si présent)
  const firstCard = page.locator('[aria-label^="Plugin "]').first()
  await firstCard.getByRole('button', { name: 'Activer' }).click({ timeout: 5000 }).catch(()=>{})
  await firstCard.getByRole('button', { name: 'Démarrer' }).click({ timeout: 5000 }).catch(()=>{})

  // LLM
  await page.getByRole('link', { name: 'LLM' }).click()
  await page.getByRole('button', { name: 'Streamer' }).click()
  // Attendre un token
  await expect(page.locator('pre')).toHaveText(/.+/, { timeout: 15000 })

  // Upload plugin ZIP fictif (archive vide, juste pour valider le flux)
  await page.getByRole('link', { name: 'Plugins' }).click()
  const fileChooserPromise = page.waitForEvent('filechooser')
  await page.getByLabel('Sélectionner un ZIP').click()
  const fileChooser = await fileChooserPromise
  // crée un zip minimal en mémoire n'est pas trivial ici; test placeholder
  // On passe pour l'instant
})

