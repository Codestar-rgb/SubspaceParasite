package com.srp.client.renderer;

import com.srp.client.model.BiomassVenkrolModel;
import com.srp.entity.BiomassVenkrolEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BiomassVenkrolRenderer extends GeoEntityRenderer<BiomassVenkrolEntity> {

    public BiomassVenkrolRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BiomassVenkrolModel());
    }
}
