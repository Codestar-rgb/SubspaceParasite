package com.srp.client.renderer;

import com.srp.client.model.BiomassModel;
import com.srp.entity.BiomassEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BiomassRenderer extends GeoEntityRenderer<BiomassEntity> {

    public BiomassRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BiomassModel());
    }
}
