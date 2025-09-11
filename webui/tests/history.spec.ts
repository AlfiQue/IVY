import { test, expect } from '@playwright/test'

test('Historique: chargement, filtres et pagination (présence UI)', async ({ page }) => {
  await page.goto('http://localhost:5173')

  // Login (utilise l’entête de l’app)
  await page.getByLabel('Utilisateur').fill('admin')
  await page.getByLabel('Mot de passe').fill('admin')
  await page.getByRole('button', { name: 'Connexion' }).click()

  // Naviguer vers Historique
  await page.getByRole('link', { name: 'Historique' }).click()

  // Vérifier présence des filtres et du total
  await expect(page.getByLabel('Filtre texte')).toBeVisible()
  await expect(page.getByLabel('Filtre plugin')).toBeVisible()
  await expect(page.locator('text=Total:')).toBeVisible()

  // Interagir avec filtres (même si aucune donnée, l’UI doit rester stable)
  await page.getByLabel('Filtre texte').fill('weather')
  await page.getByLabel('Filtre plugin').fill('weather')
  await expect(page.getByRole('button', { name: 'Précédent' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Suivant' })).toBeVisible()
})

